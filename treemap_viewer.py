#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Treemap Visualizer — Pure Python 3.10 (Tkinter)
------------------------------------------------
Features
- Treemap of files/folders sized by bytes (scaled correctly to canvas area)
- Hover tooltips, click to zoom, breadcrumb navigation, Back button
- Right-click to open with the OS default app
- Ctrl + Right-click on an item to add a quick exclude rule (folder name or *.ext)
- Exclude List UI: add absolute folders, or glob patterns (e.g., *.iso, */cache/*, node_modules)
- Folders are drawn as slightly darker shades than files (same hue palette; soft colors)
- Robust scanning (skips symlinks; handles permission errors)
"""

from __future__ import annotations

import os
import sys
import math
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.simpledialog as sd
import colorsys
import platform
import subprocess
import fnmatch
import traceback

# ---------------- Utilities ----------------

def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ["KB", "MB", "GB", "TB", "PB", "EB"]:
        n /= 1024.0
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} ZB"

def open_with_default(path: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        messagebox.showerror("Open failed", f"Could not open:\n{path}")

def pastel_color(i: int, total: int, role: str = "file") -> str:
    """
    Soft pastel palette per index; folders are a tad darker & more saturated than files.
    """
    if total <= 0:
        total = 1
    hue = (i / total) % 1.0
    l_base = 0.82
    s_base = 0.35
    if role == "dir":
        l = max(0.0, min(1.0, l_base - 0.10))
        s = max(0.0, min(1.0, s_base + 0.05))
    else:
        l = l_base
        s = s_base
    r, g, b = colorsys.hls_to_rgb(hue, l, s)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))

# ---------------- Data Model ----------------

@dataclass
class Node:
    path: str
    name: str
    size: int
    is_dir: bool
    children: List["Node"] = field(default_factory=list)

    def sorted_children(self) -> List["Node"]:
        return sorted(self.children, key=lambda n: n.size, reverse=True)

# ---------------- Directory Scanning ----------------

def scan_directory(
    root_path: str,
    stop_flag: threading.Event,
    progress_cb=None,
    exclude: Optional[Callable[[str, bool, str], bool]] = None,  # (path, is_dir, name) -> bool
) -> Node:
    """
    Recursively build a Node tree with sizes. Skips symlinks, respects excludes.
    """
    def _scan(path: str, is_root: bool = False) -> Optional[Node]:
        if stop_flag.is_set():
            raise RuntimeError("Scan stopped")

        name = os.path.basename(path) or path
        is_dir = os.path.isdir(path)

        # Skip excluded (but never exclude the chosen root)
        if not is_root and exclude and exclude(path, is_dir, name):
            return None

        try:
            st = os.lstat(path)
        except Exception:
            return Node(path, name + " [stat error]", 0, False, [])

        if os.path.islink(path):
            # Avoid cycles; don't follow links
            return Node(path, name + " [symlink]", 0, False, [])

        if is_dir:
            total = 0
            kids: List[Node] = []
            try:
                with os.scandir(path) as it:
                    for entry in it:
                        if stop_flag.is_set():
                            raise RuntimeError("Scan stopped")
                        try:
                            child = _scan(entry.path)
                            if child is not None:
                                kids.append(child)
                                total += max(child.size, 0)
                        except PermissionError:
                            kids.append(Node(entry.path, entry.name + " [denied]", 0, False, []))
                        except RuntimeError:
                            raise
                        except Exception:
                            kids.append(Node(entry.path, entry.name + " [error]", 0, False, []))
                        if progress_cb:
                            progress_cb()
            except PermissionError:
                return Node(path, name + " [denied]", 0, True, [])
            except Exception:
                return Node(path, name + " [error]", 0, True, [])
            return Node(path, name, total, True, kids)
        else:
            size = 0
            try:
                size = st.st_size
            except Exception:
                pass
            return Node(path, name, size, False, [])

    root = _scan(root_path, is_root=True)
    assert root is not None
    return root

# ---------------- Treemap Math (Squarify) ----------------

Rect = Tuple[float, float, float, float]  # (x, y, w, h)

def worst_aspect_ratio(row: List[float], short_side: float) -> float:
    if not row or short_side <= 0:
        return float("inf")
    s = sum(row)
    mx = max(row)
    mn = min(row)
    return max((short_side**2) * mx / (s**2), (s**2) / (short_side**2 * mn))

def layout_row(row: List[float], rect: Rect, horizontal: bool) -> List[Rect]:
    x, y, w, h = rect
    out: List[Rect] = []
    s = sum(row)
    if s <= 0 or w <= 0 or h <= 0:
        return out

    if horizontal:
        # Fixed height; lay items left→right
        row_h = s / w
        cx = x
        for v in row:
            rw = v / row_h
            out.append((cx, y, rw, row_h))
            cx += rw
    else:
        # Fixed width; lay items top→bottom
        col_w = s / h
        cy = y
        for v in row:
            rh = v / col_w
            out.append((x, cy, col_w, rh))
            cy += rh
    return out

def leftover_rect(rect: Rect, row: List[float], horizontal: bool) -> Rect:
    x, y, w, h = rect
    s = sum(row)
    if s <= 0 or w <= 0 or h <= 0:
        return rect
    if horizontal:
        row_h = s / w
        return (x, y + row_h, w, h - row_h)  # carve from TOP
    else:
        col_w = s / h
        return (x + col_w, y, w - col_w, h)  # carve from LEFT

def squarify(values: List[float], rect: Rect) -> List[Rect]:
    x, y, w, h = rect
    if w <= 1 or h <= 1:
        return []

    vals = [v for v in values if v > 0]
    if not vals:
        return []

    # Scale values so total area matches the rectangle area
    total = sum(vals)
    area = w * h
    scale = area / total if total > 0 else 0.0
    vals = [v * scale for v in vals]

    r: Rect = (x, y, w, h)
    row: List[float] = []
    out: List[Rect] = []

    while vals:
        rx, ry, rw, rh = r
        short = min(rw, rh)
        v = vals[0]
        if not row or worst_aspect_ratio(row + [v], short) <= worst_aspect_ratio(row, short):
            row.append(vals.pop(0))
        else:
            horizontal = (rw >= rh)
            out.extend(layout_row(row, r, horizontal))
            r = leftover_rect(r, row, horizontal)
            row = []

    if row:
        rx, ry, rw, rh = r
        horizontal = (rw >= rh)
        out.extend(layout_row(row, r, horizontal))

    return out

# ---------------- GUI ----------------

class Tooltip:
    def __init__(self, master: tk.Widget):
        self.tw: Optional[tk.Toplevel] = None
        self.master = master

    def show(self, text: str, x: int, y: int):
        self.hide()
        self.tw = tk.Toplevel(self.master)
        self.tw.wm_overrideredirect(True)
        self.tw.attributes("-topmost", True)
        label = ttk.Label(self.tw, text=text, padding=6, background="#fffffe", relief="solid", borderwidth=1)
        label.pack()
        self.tw.wm_geometry(f"+{x + 12}+{y + 12}")

    def hide(self):
        if self.tw is not None:
            self.tw.destroy()
            self.tw = None

class TreemapApp(ttk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root)
        self.root = root
        self.pack(fill="both", expand=True)

        # State
        self.current_tree: Optional[Node] = None
        self.zoom_stack: List[Node] = []
        self.rect_items: List[Tuple[int, Node, Rect]] = []
        self.stop_scan: threading.Event = threading.Event()
        self.scan_thread: Optional[threading.Thread] = None
        self.scan_count = 0
        self.scan_id = 0  # increments per scan
        self.exclude_patterns: List[str] = []

        # UI
        self._build_ui()
        self._bind_events()

    # ----- UI -----

    def _build_ui(self):
        self.root.title("Treemap Visualizer")
        self.root.geometry("1000x680")
        self.root.minsize(820, 520)

        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=8, pady=8)

        ttk.Button(top, text="Pick Folder…", command=self.pick_folder).pack(side="left")
        self.stop_btn = ttk.Button(top, text="Stop Scan", command=self.stop_scanning, state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.up_btn = ttk.Button(top, text="◀ Back", command=self.zoom_out, state="disabled")
        self.up_btn.pack(side="left", padx=(8, 0))

        self.path_var = tk.StringVar(value="No folder selected")
        ttk.Label(top, textvariable=self.path_var).pack(side="left", padx=12)

        self.size_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.size_var, foreground="#555").pack(side="right")

        # Exclude panel
        excl_wrap = ttk.Frame(self)
        excl_wrap.pack(side="top", fill="x", padx=8, pady=(0, 6))

        left = ttk.Frame(excl_wrap)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(left, text="Excluded folders,files,patterns").pack(anchor="w", padx=(2, 5))
        self.excl_list = tk.Listbox(left, height=4, selectmode=tk.EXTENDED)
        self.excl_list.pack(fill=tk.BOTH, expand=True, padx=(2, 5), pady=(2, 6))

        right = ttk.Frame(excl_wrap)
        right.pack(side=tk.LEFT, fill=tk.Y, padx=(5, 5))
        ttk.Button(right, text="Add file", command=self.on_add_excluded_file).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Add folder", command=self.on_add_excluded_folder).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Add pattern", command=self.on_add_pattern).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Remove selected", command=self.on_remove_selected_excluded).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Clear", command=self.on_clear_excluded).pack(fill=tk.X, pady=2)
        ttk.Button(right, text="Rescan", command=self.rescan_current).pack(fill=tk.X, pady=2)

        # Canvas + status
        self.breadcrumb = ttk.Frame(self)
        self.breadcrumb.pack(side="top", fill="x", padx=8)

        self.canvas = tk.Canvas(self, highlightthickness=0, background="#fafafa")
        self.canvas.pack(side="top", fill="both", expand=True, padx=8, pady=8)

        self.status = ttk.Label(self, text="Ready", anchor="w")
        self.status.pack(side="bottom", fill="x")

        self.tooltip = Tooltip(self.canvas)

        style = ttk.Style(self.root)
        try:
            if platform.system() == "Windows":
                style.theme_use("winnative")
            else:
                style.theme_use("clam")
        except tk.TclError:
            pass

    def _bind_events(self):
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Leave>", lambda e: self.tooltip.hide())
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<Button-3>", self.on_right_click)

    # ----- Exclude helpers -----

    def _get_exclude_patterns(self) -> List[str]:
        items = list(self.excl_list.get(0, tk.END))
        # Normalize: keep patterns as typed; absolute paths become normalized
        out: List[str] = []
        for p in items:
            p = p.strip()
            if not p:
                continue
            if os.path.isabs(p):
                out.append(os.path.abspath(p).replace("\\", "/"))
            else:
                out.append(p)
        return out

    def _should_exclude(self, path: str, is_dir: bool, name: str) -> bool:
        """
        - Absolute path in list: excludes that subtree/file.
        - Glob pattern on name or full normalized path: *.log, */cache/*, node_modules, .git, *.iso.
        - Plain token (no wildcards): basename equality.
        """
        path_n = os.path.abspath(path).replace("\\", "/").lower()
        name_n = name.lower()

        for pat in self.exclude_patterns:
            pat_s = pat.strip()
            if not pat_s:
                continue
            is_abs = os.path.isabs(pat_s)
            pat_n = (pat_s if not is_abs else pat_s.replace("\\", "/")).lower()

            if is_abs:
                # Absolute path rule
                base = pat_n.rstrip("/")
                if path_n == base or path_n.startswith(base + "/"):
                    return True
                continue

            # Glob on basename or full path
            if fnmatch.fnmatch(name_n, pat_n) or fnmatch.fnmatch(path_n, pat_n):
                return True

            # Plain token w/o wildcards => basename match
            if not any(ch in pat_n for ch in "*?[") and name_n == pat_n:
                return True

        return False

    def on_add_excluded_file(self):
        paths = filedialog.askopenfilenames(title="Choose file(s) to exclude")
        if not paths:
            return
        existing = set(self.excl_list.get(0, tk.END))
        for p in paths:
            norm = os.path.abspath(p).replace("\\", "/")
            if norm not in existing:
                self.excl_list.insert(tk.END, norm)
                existing.add(norm)
        # Optional: immediately rescan current folder
        self.rescan_current()

    def on_add_excluded_folder(self):
        p = filedialog.askdirectory(title="Choose folder to exclude")
        if not p:
            return
        norm = os.path.abspath(p).replace("\\", "/")
        existing = set(self.excl_list.get(0, tk.END))
        if norm not in existing:
            self.excl_list.insert(tk.END, norm)

    def on_add_pattern(self):
        pat = sd.askstring(
            "Add pattern",
            "Enter a glob pattern or name (e.g. *.iso, */cache/*, node_modules):",
        )
        if not pat:
            return
        pat = pat.strip()
        if not pat:
            return
        existing = set(self.excl_list.get(0, tk.END))
        if pat not in existing:
            self.excl_list.insert(tk.END, pat)

    def on_remove_selected_excluded(self):
        sel = list(self.excl_list.curselection())
        for i in reversed(sel):
            self.excl_list.delete(i)

    def on_clear_excluded(self):
        self.excl_list.delete(0, tk.END)

    def rescan_current(self):
        p = self.path_var.get()
        if p and os.path.isdir(p):
            self.start_scanning(p)

    # ----- Scanning control -----

    def pick_folder(self):
        path = filedialog.askdirectory(title="Select a directory")
        if not path:
            return
        self.start_scanning(path)

    def start_scanning(self, path: str):
        # Cancel previous scan (if any)
        self.stop_scanning()

        # New cancel token + generation guard ID
        stop_flag = threading.Event()
        self.stop_scan = stop_flag
        self.scan_id += 1
        current_id = self.scan_id

        # Capture current exclude rules
        self.exclude_patterns = self._get_exclude_patterns()

        # UI prep
        self.stop_btn.config(state="normal")
        self.status.config(text="Scanning…")
        self.path_var.set(path)
        self.size_var.set("")
        self.canvas.delete("all")
        self.rect_items.clear()
        self.zoom_stack.clear()
        self._draw_breadcrumb([])

        # Launch worker
        self.scan_thread = threading.Thread(
            target=self._scan_worker, args=(path, stop_flag, current_id), daemon=True
        )
        self.scan_thread.start()

    def stop_scanning(self):
        if getattr(self, "scan_thread", None) and self.scan_thread.is_alive():
            if getattr(self, "stop_scan", None):
                self.stop_scan.set()
            try:
                self.scan_thread.join(timeout=0.05)
            except Exception:
                pass
        self.stop_btn.config(state="disabled")

    def _scan_worker(self, path: str, stop_flag: threading.Event, scan_id: int):
        self.scan_count = 0

        def progress():
            if stop_flag.is_set() or scan_id != self.scan_id:
                return
            self.scan_count += 1
            if self.scan_count % 200 == 0:
                n = self.scan_count
                self.root.after(0, lambda sid=scan_id, n=n:
                                self.status.config(text=f"Scanning… ({n} items)") if sid == self.scan_id else None)

        try:
            tree = scan_directory(path, stop_flag, progress_cb=progress, exclude=self._should_exclude)
        except RuntimeError:
            if scan_id == self.scan_id:
                self.root.after(0, lambda: self.status.config(text="Scan stopped"))
            return
        except Exception as e:
            tb = traceback.format_exc()
            print(tb, file=sys.stderr)
            if scan_id == self.scan_id:
                self.root.after(0, lambda: messagebox.showerror("Scan failed", str(e)))
            return

        def apply_tree():
            if scan_id != self.scan_id or stop_flag.is_set():
                return
            self.current_tree = tree
            self.zoom_stack = [tree]
            self._update_header(tree)
            self.redraw()
            self.stop_btn.config(state="disabled")
            self.status.config(text="Done")

        self.root.after(0, apply_tree)

    # ----- Drawing -----

    def _update_header(self, node: Node):
        self.path_var.set(node.path)
        self.size_var.set(f"Total: {human_size(node.size)}")
        self._draw_breadcrumb(self.zoom_stack)

    def _draw_breadcrumb(self, nodes: List[Node]):
        for child in self.breadcrumb.winfo_children():
            child.destroy()
        if not nodes:
            self.up_btn.config(state="disabled")
            return

        def make_callback(index: int):
            def cb():
                self.zoom_stack = self.zoom_stack[: index + 1]
                self.current_tree = self.zoom_stack[-1]
                self._update_header(self.current_tree)
                self.redraw()
            return cb

        for i, n in enumerate(nodes):
            text = n.name if i > 0 else n.path
            btn = ttk.Button(self.breadcrumb, text=text, command=make_callback(i))
            btn.pack(side="left")
            if i < len(nodes) - 1:
                ttk.Label(self.breadcrumb, text=" / ").pack(side="left")

        self.up_btn.config(state="disabled" if len(nodes) <= 1 else "normal")

    def redraw(self):
        self.canvas.delete("all")
        self.rect_items.clear()
        node = self.current_tree
        if not node:
            return

        W = max(10, self.canvas.winfo_width())
        H = max(10, self.canvas.winfo_height())

        children = [c for c in node.sorted_children() if c.size > 0]
        if not children:
            self._draw_empty_message(W, H, "This folder has no sizable files.")
            return

        padding = 6
        rect_area: Rect = (padding, padding, W - 2 * padding, H - 2 * padding)
        values = [c.size for c in children]
        rects = squarify(values, rect_area)

        # Safety fallback so nothing disappears (should rarely trigger)
        if len(rects) != len(children):
            rects = []
            x, y, w, h = rect_area
            total = sum(values) or 1
            horizontal = (w >= h)
            for size in values:
                frac = size / total
                if horizontal:
                    rw = w * frac
                    rects.append((x, y, rw, h))
                    x += rw
                else:
                    rh = h * frac
                    rects.append((x, y, w, rh))
                    y += rh

        min_area_for_label = 90 * 4  # tweak if your window is smaller

        for idx, (child, r) in enumerate(zip(children, rects)):
            x, y, w, h = r
            x2, y2 = x + w, y + h
            role = "dir" if child.is_dir else "file"
            color = pastel_color(idx, len(children), role)
            outline = "#dddddd" if child.is_dir else "#ffffff"
            item = self.canvas.create_rectangle(x, y, x2, y2, fill=color, outline=outline, width=1)
            self.rect_items.append((item, child, (x, y, w, h)))

            # Label
            area = w * h
            if area >= min_area_for_label:
                icon = "📁" if child.is_dir else "📄"
                name = child.name if len(child.name) < 34 else child.name[:31] + "…"
                txt = f"{icon} {name}\n{human_size(child.size)}"
                self.canvas.create_text(
                    x + 6, y + 6, anchor="nw", text=txt, font=("Segoe UI", 9), fill="#333333"
                )

        # Hint
        self.canvas.create_text(
            W - 10,
            H - 10,
            anchor="se",
            text="Left-click to zoom • Right-click to open • Ctrl+Right-click to exclude",
            font=("Segoe UI", 8),
            fill="#777",
        )

    def _draw_empty_message(self, W: int, H: int, msg: str):
        self.canvas.create_text(W // 2, H // 2, text=msg, font=("Segoe UI", 11), fill="#666")

    # ----- Interaction -----

    def _node_at(self, event: tk.Event) -> Optional[Node]:
        x, y = event.x, event.y
        items = self.canvas.find_overlapping(x, y, x, y)
        for item in reversed(items):
            for (iid, node, _) in self.rect_items:
                if iid == item:
                    return node
        return None

    def _rect_at(self, canvas_item_id: int) -> Optional[Tuple[Node, Rect]]:
        for (iid, node, rect) in self.rect_items:
            if iid == canvas_item_id:
                return node, rect
        return None

    def on_mouse_move(self, event: tk.Event):
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item in reversed(items):
            found = self._rect_at(item)
            if found:
                node, _ = found
                kind = "Folder" if node.is_dir else "File"
                text = f"{kind}: {node.name}\n{human_size(node.size)}\n{node.path}"
                self.tooltip.show(text, event.x_root, event.y_root)
                return
        self.tooltip.hide()

    def on_left_click(self, event: tk.Event):
        node = self._node_at(event)
        if not node:
            return
        if node.is_dir and node.children:
            self.zoom_stack.append(node)
            self.current_tree = node
            self._update_header(node)
            self.redraw()

    def on_right_click(self, event: tk.Event):
        node = self._node_at(event)
        if not node:
            return

        SHIFT, CTRL = 0x0001, 0x0004
        if (event.state & CTRL):
            if (event.state & SHIFT):
                # exact absolute path rule
                rule = os.path.abspath(node.path).replace("\\", "/")
            else:
                # existing quick rule (folder name or *.ext)
                rule = node.name if node.is_dir else ("*." + node.name.rsplit(".", 1)[-1] if "." in node.name else node.name)
            existing = set(self.excl_list.get(0, tk.END))
            if rule not in existing:
                self.excl_list.insert(tk.END, rule)
            self.rescan_current()
            return

        # Normal right-click opens
        open_with_default(node.path)

    def zoom_out(self):
        if len(self.zoom_stack) > 1:
            self.zoom_stack.pop()
            self.current_tree = self.zoom_stack[-1]
            self._update_header(self.current_tree)
            self.redraw()

# ---------------- Main ----------------

def main():
    root = tk.Tk()
    app = TreemapApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
