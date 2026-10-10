-- Word positions and confidences from OCR (Azure Document Intelligence), per page.
-- Each item: {"text": "...", "confidence": 0.97, "box": [x1,y1,...,x4,y4]} with coordinates
-- normalised to 0–1 of the page, used to highlight evidence on the page image.
alter table script_pages add column words jsonb not null default '[]';
alter table script_pages add column reader text;
