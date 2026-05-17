import tkinter as tk
from gui.app import App


def main():
    root = tk.Tk()
    root.title("TLI Passive Planner")
    root.minsize(980, 640)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
