import tkinter as tk
import ctypes
from gui.app import App


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.title("TLI Planner")
    root.geometry("1280x800")
    root.minsize(1100, 680)

    try:
        scale = root.winfo_fpixels('1i') / 72.0
        root.tk.call('tk', 'scaling', scale)
    except Exception:
        pass

    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
