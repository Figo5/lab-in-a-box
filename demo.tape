# =============================================================================
# Lab-in-a-Box demo — records `demo.gif` for the README.
#
# Run from the repo root:
#     vhs demo.tape
#
# The lab should already be running (`./bin/labctl up` is idempotent, but see
# the Sleep note at the `labctl up` step if you are starting cold).
# =============================================================================

Output demo.gif

# --- capture settings -------------------------------------------------------
# NOTE: Set Width/Height are PIXELS of the recording canvas; VHS fits the
# terminal cells to that canvas (xterm.js fit). FontSize 16 + 1240x680 lands
# around a 120-column x 30-row terminal. Nudge all three together if you want
# the terminal bigger/smaller.
Set Width 1240
Set Height 680
Set FontSize 16
Set Framerate 12
Set PlaybackSpeed 1.0
Set Theme "Catppuccin Frappe"
Set WindowBar Colorful
Set Shell "bash"

# --- pipeline demo ----------------------------------------------------------

Type "./bin/labctl up"
Enter
# Fast when the lab is already up; give it more headroom if you are starting
# from cold (first boot pulls images and runs DVWA DB setup).
Sleep 18s

Type "./bin/labctl seed"
Enter
Sleep 6s

Type "./bin/labctl run-brute --target ssh-lab"
Enter
Sleep 12s

Type "./bin/labctl report"
Enter
Sleep 4s

# The report lands in the newest run dir (the one `labctl up` just created).
Type "cat runs/$(ls -t runs | head -1)/report.md"
Enter
Sleep 8s
