import os
import sys
import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import io
import urllib.request
import ttkbootstrap as tb
from tkinterdnd2 import DND_FILES, TkinterDnD
import threading
import webbrowser

VERSION = "1.0"
VERSION_URL = "https://github.com/Holland-exe/PDF-Redact/releases/download/latest/version.txt"
UPDATE_URL = "https://github.com/Holland-exe/PDF-Redact/releases/download/latest/pdfredact.exe"

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def setup_tkdnd_library():
    tkdnd_relative = os.path.join("tkdnd", "tkdnd.tcl")
    tkdnd_path = resource_path(tkdnd_relative)
    if os.path.exists(tkdnd_path):
        os.environ["TKDND_LIBRARY"] = os.path.dirname(tkdnd_path)
    else:
        raise FileNotFoundError(f"tkdnd.tcl not found at: {tkdnd_path}")

setup_tkdnd_library()

class PDFRedactorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"PDF Redact v{VERSION}")
        self.root.iconbitmap(resource_path("icon.ico"))

        self.last_bulk_action = None
        self.doc = None
        self.zoom_level = 1.0
        self.redaction_boxes = []
        self.undo_stack = []
        self.redo_stack = []
        self.start_x = self.start_y = None
        self.rect = None
        self.page_images = []
        self.page_positions = []

        self.setup_ui()
        self.check_for_updates()

    def setup_ui(self):
        self.root.geometry("1200x800")
        self.main_frame = tb.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.sidebar = tb.Frame(self.main_frame, width=160)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        self.thumb_canvas = tk.Canvas(self.sidebar, width=150, highlightthickness=0, bg="gray20")
        self.thumb_scrollbar = tb.Scrollbar(self.sidebar, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_container = tk.Frame(self.thumb_canvas, bg="gray20")

        self.thumb_container.bind(
            "<Configure>", lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))
        )
        self.thumb_canvas.create_window((0, 0), window=self.thumb_container, anchor="nw")
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scrollbar.set)
        self.thumb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.thumb_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.thumb_canvas.bind("<Enter>", lambda e: self._bind_mousewheel(self.thumb_canvas))
        self.thumb_canvas.bind("<Leave>", lambda e: self._unbind_mousewheel(self.thumb_canvas))
        content_area = tb.Frame(self.main_frame)
        content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        top_frame = tb.Frame(content_area)
        top_frame.pack(fill=tk.X, pady=5)

        tb.Button(top_frame, text="Open PDF", command=self.open_pdf, bootstyle="primary").pack(side=tk.LEFT, padx=5)
        self.save_btn = tb.Button(top_frame, text="Save Redacted PDF", command=self.save_pdf, state=tk.DISABLED, bootstyle="success")
        self.save_btn.pack(side=tk.LEFT, padx=5)
        tb.Button(top_frame, text="Undo", command=self.undo_redaction, bootstyle="warning").pack(side=tk.LEFT, padx=5)
        tb.Button(top_frame, text="Redo", command=self.redo_redaction, bootstyle="info").pack(side=tk.LEFT, padx=5)
        tb.Button(top_frame, text="Cancel All", command=self.cancel_all_selections, bootstyle="danger").pack(side=tk.LEFT, padx=5)

        # Create zoom frame on right side of top_frame
        zoom_frame = tb.Frame(top_frame)
        zoom_frame.pack(side=tk.RIGHT, padx=5)
        tb.Button(zoom_frame, text="Zoom +", command=self.zoom_in).pack(side=tk.LEFT, padx=2)
        tb.Button(zoom_frame, text="Zoom -", command=self.zoom_out).pack(side=tk.LEFT, padx=2)

        # Create update button but don't pack it yet; keep reference to zoom_frame
        self.update_btn = tb.Button(zoom_frame, text="Update Available", command=self.download_update, bootstyle="danger")
        self.zoom_frame = zoom_frame  # store zoom_frame reference for later

        self.canvas = tk.Canvas(content_area, bg="gray20", highlightthickness=0)
        self.vscroll = tb.Scrollbar(content_area, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.bind("<ButtonPress-1>", self.start_selection)
        self.canvas.bind("<B1-Motion>", self.update_selection)
        self.canvas.bind("<ButtonRelease-1>", self.finish_selection)
        self.canvas.bind("<Enter>", lambda e: self._bind_mousewheel(self.canvas))
        self.canvas.bind("<Leave>", lambda e: self._unbind_mousewheel(self.canvas))

        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.drop)

    def check_for_updates(self):
        def _check():
            try:
                with urllib.request.urlopen(VERSION_URL) as response:
                    latest_version = response.read().decode("utf-8").strip()
                    if self.is_newer_version(latest_version, VERSION):
                        self.root.after(0, lambda: self.update_btn.pack(in_=self.zoom_frame, side=tk.LEFT, padx=2))
            except Exception as e:
                print("Update check failed:", e)

        threading.Thread(target=_check, daemon=True).start()

    def is_newer_version(self, remote, local):
        def parse(v): return [int(x) for x in v.split('.')]
        return parse(remote) > parse(local)

    def download_update(self):
        webbrowser.open(UPDATE_URL)

    def _bind_mousewheel(self, widget):
        widget.bind_all("<MouseWheel>", self.mouse_scroll)

    def _unbind_mousewheel(self, widget):
        widget.unbind_all("<MouseWheel>")

    def drop(self, event):
        files = self.root.tk.splitlist(event.data)
        for f in files:
            if f.lower().endswith(".pdf"):
                self.open_pdf_path(f)
                break

    def open_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if file_path:
            self.open_pdf_path(file_path)

    def open_pdf_path(self, file_path):
        try:
            self.doc = fitz.open(file_path)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open PDF:\n{e}")
            return
        self.redaction_boxes.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.render_thumbnails()
        self.render_all_pages()
        self.save_btn.config(state=tk.NORMAL)

    def render_thumbnails(self):
        for widget in self.thumb_container.winfo_children():
            widget.destroy()
        self.thumb_images = []
        for i, page in enumerate(self.doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(0.2, 0.2))
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            tk_img = ImageTk.PhotoImage(img)
            self.thumb_images.append(tk_img)
            btn = tb.Button(self.thumb_container, image=tk_img, command=lambda idx=i: self.scroll_to_page(idx))
            btn.pack(pady=2)

    def render_all_pages(self):
        self.canvas.delete("all")
        self.page_images.clear()
        self.page_positions.clear()
        y_offset = 10
        gap = 20
        canvas_width = self.canvas.winfo_width() or 800
        for i, page in enumerate(self.doc):
            mat = fitz.Matrix(self.zoom_level, self.zoom_level)
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            tk_img = ImageTk.PhotoImage(img)
            self.page_images.append(tk_img)
            x = canvas_width // 2
            y = y_offset
            img_id = self.canvas.create_image(x, y, image=tk_img, anchor="n")
            bbox = self.canvas.bbox(img_id)
            self.page_positions.append((i, bbox))
            y_offset = bbox[3] + gap
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.update_redaction_boxes()

    def scroll_to_page(self, index):
        if index < len(self.page_positions):
            _, bbox = self.page_positions[index]
            top_y = bbox[1]
            height = self.canvas.bbox("all")[3]
            self.canvas.yview_moveto(top_y / height)

    def zoom_in(self):
        self.zoom_level *= 1.25
        self.render_all_pages()

    def zoom_out(self):
        self.zoom_level /= 1.25
        self.render_all_pages()

    def mouse_scroll(self, event):
        delta = event.delta
        if os.name == 'nt':
            self.canvas.yview_scroll(int(-1 * (delta / 120)), "units")
        else:
            self.canvas.yview_scroll(int(-1 * delta), "units")

    def start_selection(self, event):
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="red", width=2)

    def update_selection(self, event):
        if self.rect:
            cur_x = self.canvas.canvasx(event.x)
            cur_y = self.canvas.canvasy(event.y)
            self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def finish_selection(self, event):
        if not self.doc or not self.rect:
            return
        x1, y1, x2, y2 = self.canvas.coords(self.rect)
        center_y = (y1 + y2) / 2
        for page_index, bbox in self.page_positions:
            top, bottom = bbox[1], bbox[3]
            if top <= center_y <= bottom:
                left = bbox[0]
                top_page = bbox[1]
                rel_x1 = (x1 - left) / self.zoom_level
                rel_y1 = (y1 - top_page) / self.zoom_level
                rel_x2 = (x2 - left) / self.zoom_level
                rel_y2 = (y2 - top_page) / self.zoom_level
                pdf_rect = fitz.Rect(rel_x1, rel_y1, rel_x2, rel_y2)
                self.canvas.itemconfig(self.rect, outline="red", fill="black", stipple="gray50", width=2)
                self.redaction_boxes.append((page_index, pdf_rect, self.rect))
                self.undo_stack.append(("add", (page_index, pdf_rect, self.rect)))
                self.redo_stack.clear()
                self.rect = None
                break
        self.update_redaction_boxes()

    def update_redaction_boxes(self):
        # Draw black rectangles on canvas over redaction areas
        for page_index, pdf_rect, rect_id in self.redaction_boxes:
            # Canvas coords = page bbox + pdf_rect * zoom
            bbox = self.page_positions[page_index][1]
            left, top = bbox[0], bbox[1]
            x1 = left + pdf_rect.x0 * self.zoom_level
            y1 = top + pdf_rect.y0 * self.zoom_level
            x2 = left + pdf_rect.x1 * self.zoom_level
            y2 = top + pdf_rect.y1 * self.zoom_level
            self.canvas.coords(rect_id, x1, y1, x2, y2)
            self.canvas.itemconfig(rect_id, fill="black", stipple="gray50", outline="red")

    def undo_redaction(self):
        if not self.undo_stack:
            return
        action, data = self.undo_stack.pop()
        if action == "add":
            if data in self.redaction_boxes:
                self.redaction_boxes.remove(data)
                self.canvas.delete(data[2])
            self.redo_stack.append(("add", data))
        self.update_redaction_boxes()

    def redo_redaction(self):
        if not self.redo_stack:
            return
        action, data = self.redo_stack.pop()
        if action == "add":
            page_index, pdf_rect, old_rect_id = data

        # Get page bbox on canvas
        bbox = self.page_positions[page_index][1]
        left, top = bbox[0], bbox[1]
        x1 = left + pdf_rect.x0 * self.zoom_level
        y1 = top + pdf_rect.y0 * self.zoom_level
        x2 = left + pdf_rect.x1 * self.zoom_level
        y2 = top + pdf_rect.y1 * self.zoom_level

        # Create new rectangle on canvas (matching the previous)
        new_rect_id = self.canvas.create_rectangle(x1, y1, x2, y2, fill="black", stipple="gray50", outline="red", width=2)

        new_data = (page_index, pdf_rect, new_rect_id)
        self.redaction_boxes.append(new_data)
        self.undo_stack.append(("add", new_data))

        self.update_redaction_boxes()


    def cancel_all_selections(self):
        for _, _, rect_id in self.redaction_boxes:
            self.canvas.delete(rect_id)
        self.redaction_boxes.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()

    def save_pdf(self):
        if not self.doc or not self.redaction_boxes:
            messagebox.showwarning("Warning", "No PDF loaded or no redactions made.")
            return
        save_path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                                 filetypes=[("PDF files", "*.pdf")])
        if not save_path:
            return

        doc_copy = fitz.open()
        for i in range(len(self.doc)):
            doc_copy.insert_pdf(self.doc, from_page=i, to_page=i)

        for page_index, rect, _ in self.redaction_boxes:
            page = doc_copy[page_index]
            page.add_redact_annot(rect, fill=(0, 0, 0))
        for page in doc_copy:
            page.apply_redactions()

        try:
            doc_copy.save(save_path)
            messagebox.showinfo("Success", "Redacted PDF saved successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save PDF:\n{e}")
        finally:
            doc_copy.close()

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    style = tb.Style("darkly")
    app = PDFRedactorApp(root)
    root.mainloop()
