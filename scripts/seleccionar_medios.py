"""Selector de archivos del editor, desacoplado para que funcione también congelado."""
import json
import tkinter as tk
from tkinter import filedialog

root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
paths = filedialog.askopenfilenames(
    title="Elige videos, imágenes o audios",
    filetypes=[
        ("Videos, imágenes y audios", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.png *.jpg *.jpeg *.webp *.gif *.mp3 *.wav *.m4a *.aac *.ogg *.opus *.flac"),
        ("Todos", "*.*"),
    ],
)
print(json.dumps(list(paths)))
root.destroy()
