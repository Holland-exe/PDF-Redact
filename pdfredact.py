import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import io
import os
from tkinterdnd2 import DND_FILES, TkinterDnD
import ttkbootstrap as tb  # Modern themed ttk replacement


class PDFRedactorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Redact Pro")

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

    def setup_ui(self):
        self.root.geometry("1200x800")
        self.main_frame = tb.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Sidebar for thumbnails - made wider (150 instead of 120)
        self.sidebar = tb.Frame(self.main_frame, width=150)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        self.thumb_canvas = tk.Canvas(self.sidebar, width=140, highlightthickness=0)
        self.thumb_scrollbar = tb.Scrollbar(self.sidebar, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_container = tb.Frame(self.thumb_canvas)

        self.thumb_container.bind(
            "<Configure>", lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))
        )
        self.thumb_canvas.create_window((0, 0), window=self.thumb_container, anchor="nw")
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scrollbar.set)

        self.thumb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.thumb_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind mouse wheel scrolling only for thumbnails when hovered
        self.thumb_canvas.bind("<Enter>", lambda e: self.thumb_canvas.bind_all("<MouseWheel>", self.thumb_mouse_scroll))
        self.thumb_canvas.bind("<Leave>", lambda e: self.thumb_canvas.unbind_all("<MouseWheel>"))

        # Content area
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

        tb.Button(top_frame, text="Zoom +", command=self.zoom_in).pack(side=tk.RIGHT, padx=5)
        tb.Button(top_frame, text="Zoom -", command=self.zoom_out).pack(side=tk.RIGHT, padx=5)

        # Scrollable canvas for pages
        self.canvas = tk.Canvas(content_area, bg="gray20", highlightthickness=0)
        self.vscroll = tb.Scrollbar(content_area, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas.bind("<ButtonPress-1>", self.start_selection)
        self.canvas.bind("<B1-Motion>", self.update_selection)
        self.canvas.bind("<ButtonRelease-1>", self.finish_selection)
        self.canvas.bind_all("<MouseWheel>", self.mouse_scroll)

        # Drag & drop support
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self.drop)

    def thumb_mouse_scroll(self, event):
        delta = event.delta
        if os.name == 'nt':
            self.thumb_canvas.yview_scroll(int(-1 * (delta / 120)), "units")
        else:
            self.thumb_canvas.yview_scroll(int(-1 * delta), "units")

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

        # Draw redaction boxes on canvas as translucent black rectangles
        for page_index, rect in self.redaction_boxes:
            # Get canvas coordinates of the page image
            _, bbox = self.page_positions[page_index]
            left = bbox[0]
            top = bbox[1]

            # Convert PDF rect to canvas coords
            x1 = left + rect.x0 * self.zoom_level
            y1 = top + rect.y0 * self.zoom_level
            x2 = left + rect.x1 * self.zoom_level
            y2 = top + rect.y1 * self.zoom_level

            self.canvas.create_rectangle(x1, y1, x2, y2, fill="black", stipple="gray50", outline="")

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

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
                self.redaction_boxes.append((page_index, pdf_rect))
                self.undo_stack.append((page_index, pdf_rect))
                self.redo_stack.clear()  # Clear redo stack after new action
                self.canvas.itemconfig(self.rect, fill="black", stipple="gray50")
                break

    def undo_redaction(self):
        if self.undo_stack:
            last = self.undo_stack.pop()
            self.redo_stack.append(last)
            if last in self.redaction_boxes:
                self.redaction_boxes.remove(last)
            self.render_all_pages()  # re-render to remove the visual box

    def redo_redaction(self):
        if self.redo_stack:
            last = self.redo_stack.pop()
            self.redaction_boxes.append(last)
            self.undo_stack.append(last)
            self.render_all_pages()

    def cancel_all_selections(self):
        if not self.redaction_boxes:
            return
        if messagebox.askyesno("Cancel All", "Are you sure you want to cancel all redaction selections?"):
            self.redaction_boxes.clear()
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.render_all_pages()

    def save_pdf(self):
        if not self.doc or not self.redaction_boxes:
            messagebox.showwarning("Nothing to Redact", "No redactions were made.")
            return

        for page_index, rect in self.redaction_boxes:
            page = self.doc[page_index]
            page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()

        save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if save_path:
            self.doc.save(save_path)
            messagebox.showinfo("Success", "Redacted PDF saved.")


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    tb.Style("superhero")  # Options: superhero, flatly, darkly, cyborg, etc.
    app = PDFRedactorApp(root)
    root.mainloop()
