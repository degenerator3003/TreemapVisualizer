# Treemap Visualizer (Pure Python 3.10 + Tkinter)

A fast, dependency-free treemap visualizer for disk usage.
Pick a folder and see files/folders as soft, colorful rectangles sized by bytes.
Hover for details, click to zoom into folders, and exclude noisy paths/patterns to keep the view focused.

> ✅ Pure standard library (Tkinter)
> ✅ Works on Windows, macOS, Linux
> ✅ No flashy colors—folders are subtly darker than files

---

## Features

* **Treemap layout (squarified)** scaled precisely to the canvas area—big files look big, smaller ones stay visible.
* **Interactive navigation**: hover tooltip; **left-click** to drill into a folder; **Back** button + breadcrumb to go up.
* **Open with default app**: **right-click** a file/folder to open it in your OS.
* **Exclude anything** to “trim the fat”:

  * **Add File…** / **Add Folder…** buttons for absolute paths.
  * **Add Pattern…** for glob rules like `*.iso`, `*/cache/*`, `node_modules`, `.git`.
  * **Ctrl + Right-click** on a rectangle to quickly add `foldername` or `*.ext`.
  * **Ctrl + Shift + Right-click** to add the exact absolute path.
* **Robust scanning**:

  * Per-scan cancellation & generation guard (starting a new scan cancels the old one).
  * Skips symlinks (prevents cycles).
  * Handles permission errors without crashing (marks entries as `[denied]` or `[error]`).

---

## Screenshots

> (Add your screenshots here once you have them.)

---

## Requirements

* **Python 3.10+**
* **Tkinter** (bundled with most Python installers)

  * Windows/macOS official Python builds include Tkinter.
  * On some Linux distros you may need `python3-tk` (e.g., `sudo apt install python3-tk`).

No third-party packages required.

---

## Installation

Clone your repo and run the script:

```bash
git clone https://github.com/Degenerator3003/TreemapVisualizer.git
cd TreemapVisualizer
python treemap_viewer.py
```

On Windows you can double-click `treemap_viewer.py` if `.py` files are associated with Python.

---

## Usage

1. **Pick Folder…** – choose the root directory to visualize.
2. Watch the treemap fill in. Use:

   * **Left-click** a folder rectangle to **zoom in**.
   * **◀ Back** or the **breadcrumb** to go up.
   * **Right-click** any item to **open** it in your OS.
3. **Excluding clutter** (keeps the view focused and speeds up scans):

   * **Add File…** / **Add Folder…**: adds absolute paths to the exclude list.
   * **Add Pattern…**: add glob rules like:

     * `*.iso`, `*.zip`, `*.log` (by extension)
     * `node_modules`, `.git`, `__pycache__` (by name)
     * `*/cache/*`, `*/venv/*` (path patterns)
   * **Remove selected** / **Clear** to edit the list.
   * **Rescan** to re-run the scan with current rules.
   * Quick shortcuts on the treemap:

     * **Ctrl + Right-click**: add `foldername` or `*.ext`
     * **Ctrl + Shift + Right-click**: add exact absolute path

### Tips

* **Stop Scan** cancels long scans (e.g., when you mistakenly pick the whole disk).
* Labels appear only when a rectangle has enough area; resize the window to reveal more labels.

---

## Keyboard & Mouse Reference

* **Hover**: show tooltip with kind, name, size, full path
* **Left-click**: zoom into folders
* **◀ Back / breadcrumb**: navigate up
* **Right-click**: open with the OS (Explorer/Finder/xdg-open)
* **Ctrl + Right-click**: add quick exclude (`foldername` or `*.ext`)
* **Ctrl + Shift + Right-click**: add exact absolute path to excludes

---

## How Exclusion Rules Work

* **Absolute paths** (from “Add File…” / “Add Folder…”): exclude that file or the entire subtree under that folder.
* **Glob patterns** (from “Add Pattern…”): matched against both basename and full normalized path:

  * Examples: `*.iso`, `*/cache/*`, `node_modules`, `.git`
* **Plain tokens** (no wildcards): must equal the item’s basename (case-insensitive).

---

## Technical Notes

* **Color palette**: soft HLS pastels; **folders** are slightly darker/more saturated than files for subtle contrast.
* **Layout**: squarified treemap with correct scaling to the drawing area; stable orientation per remaining rectangle.
* **Sizes**: uses `os.lstat(...).st_size` for files; directory sizes are the sum of visible (non-excluded) children.
* **Symlinks**: detected and *not followed* to avoid cycles; shown as zero-size entries with a `[symlink]` marker.
* **Resilience**: permission errors and odd filesystem states are handled gracefully and annotated in the UI.

---

## Packaging (optional)

If you’d like a single executable (no Python installed):

* **PyInstaller** (3rd-party):

  ```bash
  pip install pyinstaller
  pyinstaller --noconsole --onefile treemap_viewer.py
  ```

  The resulting binary will be in `dist/`.

---

## Known Limitations

* On directories with millions of tiny files, drawing/labeling every rectangle can be heavy; use excludes to focus.
* File sizes reflect *logical* size (`st_size`), not allocated disk blocks.
* Network drives or protected system folders may report `[denied]` or `[error]` entries; the app continues.

---

## Getting Started Quickly

1. Run `treemap_viewer.py`.
2. Click **Pick Folder…** (e.g., your Downloads).
3. Add patterns: `.git,__pycache__,node_modules,*.zip,*.iso,*/cache/*`
4. Click **Rescan**.
5. Explore and drill down with left-click; open items with right-click.

---

## License

Specify your preferred license (e.g., MIT) and include a `LICENSE` file in the repo.

---

## Contributing

Issues and PRs are welcome! Ideas: dark mode, export image, “Other bucket” for tiny files, extension legend, search/filter.

---

## Acknowledgments

* Treemap concept: squarified layout (Bruls, Huizing, van Wijk).
* Built with Python’s standard **Tkinter**—no external UI frameworks.


