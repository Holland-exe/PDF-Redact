import fitz  # PyMuPDF
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import io
import os
from tkinterdnd2 import DND_FILES, TkinterDnD

class PDFRedactorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Redact")

        # Set window icon if exists
        icon_path = ".png"
        if os.path.exists(icon_path):
            try:
                icon_img = Image.open(icon_path)
                icon_tk = ImageTk.PhotoImage(icon_img)
                self.root.iconphoto(False, icon_tk)
            except Exception as e:
                print(f"Could not set icon: {e}")

        self.doc = None
        self.zoom_level = 1.0
        self.redaction_boxes = []

        self.start_x = self.start_y = None
        self.rect = None

        self.page_images = []  # Store PhotoImage for each page
        self.page_positions = []  # Y offsets for each page on canvas

        self.setup_ui()

    def setup_ui(self):
        self.root.geometry("1200x800")
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Sidebar for thumbnails
        self.sidebar = ttk.Frame(self.main_frame, width=120)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        self.thumb_canvas = tk.Canvas(self.sidebar, width=110, highlightthickness=0)
        self.thumb_scrollbar = ttk.Scrollbar(self.sidebar, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_container = ttk.Frame(self.thumb_canvas)

        self.thumb_container.bind(
            "<Configure>", lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))
        )
        self.thumb_canvas.create_window((0, 0), window=self.thumb_container, anchor="nw")
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scrollbar.set)

        self.thumb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.thumb_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Content area
        content_area = ttk.Frame(self.main_frame)
        content_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        top_frame = ttk.Frame(content_area)
        top_frame.pack(fill=tk.X, pady=5)

        ttk.Button(top_frame, text="Open PDF", command=self.open_pdf).pack(side=tk.LEFT, padx=5)
        self.save_btn = ttk.Button(top_frame, text="Save Redacted PDF", command=self.save_pdf, state=tk.DISABLED)
        self.save_btn.pack(side=tk.LEFT)

        ttk.Button(top_frame, text="Zoom +", command=self.zoom_in).pack(side=tk.RIGHT, padx=5)
        ttk.Button(top_frame, text="Zoom -", command=self.zoom_out).pack(side=tk.RIGHT)

        # Scrollable canvas for pages
        self.canvas = tk.Canvas(content_area, bg="gray", highlightthickness=0)
        self.vscroll = ttk.Scrollbar(content_area, orient=tk.VERTICAL, command=self.canvas.yview)
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

    def drop(self, event):
        files = self.root.tk.splitlist(event.data)
        for f in files:
            if f.lower().endswith(".pdf"):
                self.open_pdf_path(f)
                break

    def open_pdf(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not file_path:
            return
        self.open_pdf_path(file_path)

    def open_pdf_path(self, file_path):
        try:
            self.doc = fitz.open(file_path)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open PDF:\n{e}")
            return

        self.redaction_boxes.clear()
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

            btn = ttk.Button(self.thumb_container, image=tk_img, command=lambda idx=i: self.scroll_to_page(idx))
            btn.pack(pady=2)

    def render_all_pages(self):
        self.canvas.delete("all")
        self.page_images.clear()
        self.page_positions.clear()

        y_offset = 10
        gap = 20
        canvas_width = self.canvas.winfo_width() or 800  # fallback width

        for i, page in enumerate(self.doc):
            mat = fitz.Matrix(self.zoom_level, self.zoom_level)
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            tk_img = ImageTk.PhotoImage(img)
            self.page_images.append(tk_img)

            # Center pages horizontally
            x = canvas_width // 2
            y = y_offset

            # Create image on canvas anchored by center top
            img_id = self.canvas.create_image(x, y, image=tk_img, anchor="n")

            # Store position and page info (top-left corner)
            bbox = self.canvas.bbox(img_id)
            self.page_positions.append((i, bbox))

            y_offset = bbox[3] + gap

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def scroll_to_page(self, index):
        if index < len(self.page_positions):
            _, bbox = self.page_positions[index]
            top_y = bbox[1]
            height = self.canvas.bbox("all")[3]
            if height > 0:
                self.canvas.yview_moveto(top_y / height)

    def zoom_in(self):
        self.zoom_level *= 1.25
        self.render_all_pages()

    def zoom_out(self):
        self.zoom_level /= 1.25
        self.render_all_pages()

    def mouse_scroll(self, event):
        delta = event.delta
        if os.name == 'nt':  # Windows
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

        # Find which page the selection falls on by Y coordinate within page bbox
        for page_index, bbox in self.page_positions:
            top, bottom = bbox[1], bbox[3]
            if top <= center_y <= bottom:
                # Calculate PDF coords:
                # Canvas bbox: (left, top, right, bottom)
                left = bbox[0]
                top_page = bbox[1]

                rel_x1 = (x1 - left) / self.zoom_level
                rel_y1 = (y1 - top_page) / self.zoom_level
                rel_x2 = (x2 - left) / self.zoom_level
                rel_y2 = (y2 - top_page) / self.zoom_level

                pdf_rect = fitz.Rect(rel_x1, rel_y1, rel_x2, rel_y2)
                self.redaction_boxes.append((page_index, pdf_rect))

                self.canvas.itemconfig(self.rect, fill="black", stipple="gray50")
                break

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
    app = PDFRedactorApp(root)
    root.mainloop()
