# PDF Redactor

A simple Windows desktop application to securely redact text or areas in PDF files.  
Select text visually to redact it irreversibly and save the redacted PDF.

---

## Features

- Open PDF files via file dialog or drag-and-drop
- View all pages with thumbnails sidebar and page navigation
- Select multiple rectangular areas on any page to redact (with mouse drag)
- Irreversible redaction: removes underlying content, not just hides it
- Zoom in/out PDF pages for precise selection
- Scroll vertically through pages using mouse wheel
- Save redacted PDF as a new file

---

## Requirements

- Python 3.7+
- Dependencies:
  - [PyMuPDF (fitz)](https://pypi.org/project/PyMuPDF/)
  - [Pillow](https://pypi.org/project/Pillow/)
  - [tkinterdnd2](https://pypi.org/project/tkinterdnd2/) (for drag & drop support)

Install dependencies with:

```bash
pip install pymupdf pillow tkinterdnd2
