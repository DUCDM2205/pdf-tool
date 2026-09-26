"""Page reconstruction, selective editing and native PDF objects.
All edits are made on an isolated copy and committed only after validation.
"""
from __future__ import annotations
import base64, html, io, math, re, shutil, subprocess, tempfile, uuid
from pathlib import Path
import fitz
from pdf_engine import InputError, build_pdf, FONT_PATH


def document(entry, sources):
    doc = fitz.open(stream=build_pdf([entry], sources), filetype='pdf')
    doc[0].remove_rotation()
    return doc


def number(value, minimum, maximum):
    value = float(value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise InputError(f'Giá trị phải từ {minimum} đến {maximum}.')
    return value


def rectangle(value, page):
    if not isinstance(value, list) or len(value) != 4:
        raise InputError('Cần chọn vùng trên trang.')
    r = fitz.Rect([number(x, -10000, 10000) for x in value])
    if r.is_empty or not page.rect.contains(r):
        raise InputError('Vùng chọn phải nằm trong trang và có kích thước dương.')
    return r


def blocks(page):
    result = []
    hidden=[fitz.Rect(t['bbox']) for t in page.get_texttrace() if t['type']==3]
    for b in page.get_text('dict')['blocks']:
        if b['type'] != 0:
            continue
        spans = [s for line in b['lines'] for s in line['spans']]
        if not spans:
            continue
        s = spans[0]
        result.append({'id': str(b['number']), 'bbox': list(b['bbox']),
            'text': '\n'.join(''.join(s['text'] for s in line['spans']) for line in b['lines']),
            'ocr': any(fitz.Rect(b['bbox']).intersects(r) for r in hidden), 'font': s['font'], 'size': s['size'], 'color': '#%06x' % s['color'],
            'bold': bool(s['flags'] & 16), 'italic': bool(s['flags'] & 2),
            'spans': [dict(text=s['text'], bbox=list(s['bbox']),font=s['font'],size=s['size'],flags=s['flags']) for s in spans],
            'direction': list(b['lines'][0]['dir'])})
    # OCR's glyph bbox differs from the ink bbox in the scan. Retain the ink
    # rectangle separately to remove all original pixels when editing OCR text.
    regions=[a.rect for a in page.annots() or [] if a.info.get('title')=='FridayOCR']
    for b in result:
        if b.get('ocr'):
            matches=[r for r in regions if r.intersects(fitz.Rect(b['bbox']))]
            if matches:
                ink=fitz.Rect(b['bbox'])
                for r in matches: ink |= r
                b['bbox']=list(ink & page.rect)
                b['inkBbox']=list(ink & page.rect)
    return result


def scan(entry, sources):
    with document(entry, sources) as doc:
        page = doc[0]
        text = blocks(page)
        images = []
        # xrefs can occur multiple times: target an occurrence by its rectangle.
        for i, info in enumerate(page.get_image_info(xrefs=True)):
            images.append({'id': str(i), 'bbox': list(info['bbox']), 'xref': info['xref'],
                           'width': info['width'], 'height': info['height']})
        tables = []
        try:
            for i, table in enumerate(page.find_tables().tables):
                tables.append({'id': str(i), 'bbox': list(table.bbox), 'rows': table.extract()})
        except Exception:
            pass
        forms = [{'id': w.xref, 'bbox': list(w.rect), 'name': w.field_name,
                  'value': w.field_value or '', 'type': w.field_type_string} for w in page.widgets() or []]
        candidates = []
        for b in text:
            for span in b['spans']:
                if re.search(r'\.{4,}|_{4,}|…{2,}', span['text']):
                    candidates.append({'bbox':span['bbox'], 'reason':'Dòng chấm hoặc gạch dưới'})
        for d in page.get_drawings():
            for item in d['items']:
                if item[0] == 're':
                    r = item[1]
                    if 25 < r.width < page.rect.width*.9 and 10 < r.height < 55 and not any(r.intersects(fitz.Rect(b['bbox'])) for b in text):
                        candidates.append({'bbox': list(r), 'reason':'Ô chữ nhật trống'})
        candidates = [c for c in candidates if not any(fitz.Rect(c['bbox']).intersects(fitz.Rect(f['bbox'])) for f in forms)]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.4,1.4), alpha=False)
        return {'width':page.rect.width,'height':page.rect.height,'text':text,'images':images,
                'tables':tables,'forms':forms,'formCandidates':candidates[:100],
                'fonts':[{'xref':f[0],'name':f[3],'resource':f[4],'embedded':bool(f[1])} for f in page.get_fonts()],
                'graphics':[{'bbox':list(d['rect']),'type':d['type'],'width':d.get('width')} for d in page.get_drawings()],
                'headers':[b['id'] for b in text if b['bbox'][1]<36],
                'footers':[b['id'] for b in text if b['bbox'][3]>page.rect.height-36],
                'preview':'data:image/png;base64,'+base64.b64encode(pix.tobytes('png')).decode()}


def ensure_space(page, target, originals=(), images=False):
    for b in blocks(page):
        for s in b['spans']:
            r = fitz.Rect(s['bbox'])
            if any(o.contains(r) or (o & r).get_area() > r.get_area()*.85 for o in originals):
                continue
            if (r & target).get_area() > .2:
                raise InputError('Vùng mới đè lên chữ khác. Hãy thu nhỏ vùng hoặc giảm cỡ chữ.')
    if images:
        for info in page.get_image_info():
            r = fitz.Rect(info['bbox'])
            # Text already overlapping an image may be edited in place (backgrounds,
            # scanned pages with text layers, letterheads). Preserve that image.
            existing_overlap = any((r & o).get_area() > .2 for o in originals)
            if (r & target).get_area() > .2 and not existing_overlap:
                raise InputError('Vùng chữ mới đè lên hình ảnh. Nếu muốn đặt chữ trên ảnh, bật “Cho phép đặt chữ lên ảnh”; hoặc chọn vùng khác.')


def insert_text(page, rect, text, options):
    size = number(options.get('size',12), 4, 160)
    color = options.get('color','#182538')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',color):
        raise InputError('Màu chữ không hợp lệ.')
    if len(text)>30000:
        raise InputError('Mỗi vùng tối đa 30.000 ký tự.')
    # Font files are embedded in the new PDF, including Vietnamese glyphs.
    family=options.get('family','DejaVuSans')
    if family not in {'DejaVuSans','DejaVuSerif','DejaVuSansMono'}:raise InputError('Font không hợp lệ.')
    italic='Italic' if family=='DejaVuSerif' else 'Oblique'
    face=family+('-Bold'+italic if options.get('bold') and options.get('italic') else '-Bold' if options.get('bold') else '-'+italic if options.get('italic') else '')+'.ttf'
    css = '@font-face {font-family: Friday; src: url('+face+');} * {font-family: Friday;} body {margin:0;font-size:'+str(size)+'pt;line-height:1.15;color:'+color+';}'
    content = '<div>'+html.escape(text).replace('\n','<br>')+'</div>'
    spare, scale = page.insert_htmlbox(rect, content, css=css, archive=fitz.Archive(str(FONT_PATH.parent)), scale_low=1)
    if spare < 0:
        raise InputError('Chữ không vừa vùng đã chọn. Tăng chiều rộng/cao hoặc giảm cỡ chữ; thay đổi chưa được lưu.')


def image_bytes(value):
    if not isinstance(value,str) or not re.match(r'^data:image/(png|jpeg|webp);base64,',value):
        raise InputError('Chọn ảnh PNG, JPG hoặc WebP.')
    raw=base64.b64decode(value.split(',',1)[1],validate=True)
    if len(raw)>10*1024*1024:
        raise InputError('Ảnh tối đa 10 MB.')
    return raw


def erase(page, rects, images=0, graphics=0, fill=False, text=0):
    for r in rects:
        page.add_redact_annot(r, fill=fill, cross_out=False)
    page.apply_redactions(images=images,graphics=graphics,text=text)


def edit(entry, sources, operation):
    with document(entry, sources) as doc:
        page=doc[0]
        kind=operation.get('kind')
        if kind in ('text','addText'):
            originals=[]; is_ocr=False
            if kind=='text':
                found=next((b for b in blocks(page) if b['id']==str(operation.get('id'))),None)
                if found is None: raise InputError('Vùng chữ đã thay đổi; hãy chọn lại.')
                if abs(found['direction'][1])>.01:
                    raise InputError('Chữ xoay/nghiêng chưa thể thay trực tiếp. Dùng che vùng và thêm chữ mới.')
                originals=[fitz.Rect(s['bbox']) for s in found['spans']]
                is_ocr=found.get('ocr',False)
                if is_ocr and found.get('inkBbox'): originals=[fitz.Rect(found['inkBbox'])]
            target=rectangle(operation['bbox'],page)
            ensure_space(page,target,originals,images=not is_ocr and not bool(operation.get('allowImageOverlap',False)))
            if originals:
                # Small inward inset prevents touching a neighbouring line boundary.
                erase(page,[r if is_ocr else r+(.1,.1,-.1,-.1) for r in originals],images=2 if is_ocr else 0,fill=(1,1,1) if is_ocr else False)
                if is_ocr:
                    for a in list(page.annots() or []):
                        if a.info.get('title')=='FridayOCR' and any(a.rect.intersects(r) for r in originals):page.delete_annot(a)
            if operation.get('text'):
                insert_text(page,target,str(operation['text']),operation)
        elif kind in ('image','addImage','signature'):
            target=rectangle(operation['bbox'],page)
            raw=None
            if kind=='image':
                infos=page.get_image_info(xrefs=True)
                idx=int(operation['id'])
                if not 0<=idx<len(infos): raise InputError('Ảnh đã thay đổi; hãy chọn lại.')
                info=infos[idx]; original=fitz.Rect(info['bbox'])
                if not operation.get('delete'):
                    ensure_space(page,target,[original])
                    if operation.get('image'): raw=image_bytes(operation['image'])
                    elif info['xref']:
                        extracted=doc.extract_image(info['xref']);raw=extracted['image']
                        if extracted.get('smask'):
                            pix=fitz.Pixmap(doc,info['xref']);mask=fitz.Pixmap(doc,extracted['smask'])
                            raw=fitz.Pixmap(pix,mask).tobytes('png')
                    else: raise InputError('Ảnh inline cần tải ảnh thay thế lên.')
                # Pixel removal at this occurrence, preserving text and vector paths.
                erase(page,[original],images=2,graphics=0,text=1)
            else: raw=image_bytes(operation['image'])
            if raw:
                if operation.get('crop'):
                    from PIL import Image
                    with Image.open(io.BytesIO(raw)) as im:
                        l,t,r,b=[number(v,0,100) for v in operation['crop']]
                        if l+r>=100 or t+b>=100: raise InputError('Lề cắt ảnh quá lớn.')
                        im=im.crop((im.width*l/100,im.height*t/100,im.width*(1-r/100),im.height*(1-b/100)))
                        buf=io.BytesIO();im.save(buf,'PNG');raw=buf.getvalue()
                page.insert_image(target,stream=raw,keep_proportion=bool(operation.get('keepRatio',True)))
        elif kind=='redact':
            target=rectangle(operation['bbox'],page)
            for widget in list(page.widgets() or []):
                if widget.rect.intersects(target):page.delete_widget(widget)
            for annot in list(page.annots() or []):
                if annot.rect.intersects(target):page.delete_annot(annot)
            erase(page,[target],images=2,graphics=2,fill=(0,0,0))
            doc.scrub(attached_files=True,embedded_files=True,hidden_text=True,metadata=True,redactions=True,remove_links=True,reset_fields=False,reset_responses=True,thumbnails=True,xml_metadata=True)
        elif kind=='table':
            target=rectangle(operation['bbox'],page)
            rows=operation.get('rows')
            if not isinstance(rows,list) or not 1<=len(rows)<=100 or not all(isinstance(r,list) for r in rows):raise InputError('Bảng cần 1–100 hàng.')
            cols=max(map(len,rows),default=0)
            if not 1<=cols<=30:raise InputError('Bảng cần 1–30 cột.')
            originals=[]
            if operation.get('id') is not None:
                tables=page.find_tables().tables
                idx=int(operation['id'])
                if not 0<=idx<len(tables):raise InputError('Bảng đã thay đổi; hãy chọn lại.')
                originals=[fitz.Rect(tables[idx].bbox)]
            ensure_space(page,target,originals,images=True)
            if originals:erase(page,originals,graphics=1)
            w,h=target.width/cols,target.height/len(rows)
            for i,row in enumerate(rows):
                for j in range(cols):
                    cell=fitz.Rect(target.x0+j*w,target.y0+i*h,target.x0+(j+1)*w,target.y0+(i+1)*h)
                    page.draw_rect(cell,color=(.35,.4,.5),width=.5)
                    val=str(row[j] or '') if j<len(row) else ''
                    if val:insert_text(page,cell+(3,2,-3,-2),val,operation)
        elif kind=='form':
            target=rectangle(operation['bbox'],page)
            if operation.get('id'):
                widget=page.load_widget(int(operation['id']))
                if not widget:raise InputError('Trường dữ liệu không tồn tại.')
                if widget.field_type!=fitz.PDF_WIDGET_TYPE_TEXT:raise InputError('Hiện chỉ chỉnh giá trị trường Text.')
                widget.field_value=str(operation.get('text',''));widget.update()
            else:
                widget=fitz.Widget();widget.field_type=fitz.PDF_WIDGET_TYPE_TEXT
                widget.field_name='Friday_'+uuid.uuid4().hex[:12]
                widget.rect=target;widget.field_value=str(operation.get('text',''))
                widget.text_font='Helv';widget.text_fontsize=11
                page.add_widget(widget)
        elif kind=='removeWatermark':
            # Only explicitly selected candidates; never run during upload.
            for item in operation.get('items',[]):
                target=rectangle(item['bbox'],page)
                if item['type']=='text': erase(page,[target])
                elif item['type']=='image':erase(page,[target],images=2,text=1)
        elif kind=='ocr':
            run_ocr(page,operation)
        else:raise InputError('Thao tác không được hỗ trợ.')
        return doc.tobytes(garbage=4,deflate=True,clean=True)


def run_ocr(page,options):
    executable=shutil.which('tesseract')
    if not executable:
        for path in [Path('C:/Program Files/Tesseract-OCR/tesseract.exe'),Path('C:/Program Files (x86)/Tesseract-OCR/tesseract.exe')]:
            if path.exists():executable=str(path);break
    if not executable:raise InputError('Chưa cài Tesseract OCR. Xem INSTALL.md rồi khởi động lại ứng dụng.')
    language=options.get('language','eng')
    if not re.fullmatch(r'[a-z_+]{3,40}',language):raise InputError('Ngôn ngữ OCR không hợp lệ.')
    import csv
    with tempfile.TemporaryDirectory(prefix='friday-ocr-') as temp:
        file=Path(temp)/'page.png'
        scale=2
        page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).save(file)
        result=subprocess.run([executable,str(file),'stdout','-l',language,'tsv'],capture_output=True,timeout=120)
        if result.returncode:raise InputError('OCR không chạy được. Kiểm tra gói ngôn ngữ '+language+'. '+result.stderr.decode(errors='replace')[-300:])
        lines={}
        for row in csv.DictReader(io.StringIO(result.stdout.decode('utf-8')),delimiter='\t',quoting=csv.QUOTE_NONE):
            if not row.get('text','').strip() or float(row['conf'])<35:continue
            key=tuple(row[k] for k in ('block_num','par_num','line_num'))
            x,y,w,h=[int(row[k])/scale for k in ('left','top','width','height')]
            r=fitz.Rect(x,y,x+w,y+h)
            if key not in lines:lines[key]=[r,[]]
            lines[key][0]|=r;lines[key][1].append(row['text'])
        existing=[fitz.Rect(s['bbox']) for b in blocks(page) for s in b['spans']]
        count=0
        for r,words in lines.values():
            if any(r.intersects(e) for e in existing):continue
            text=' '.join(words)
            size=max(5,min(48,r.height*.85))
            font=fitz.Font(fontfile=str(FONT_PATH))
            size=min(size,r.width/max(font.text_length(text,fontsize=1),1))
            page.insert_font(fontname='FridayOCR',fontfile=str(FONT_PATH))
            page.insert_text((r.x0,r.y1),text,fontname='FridayOCR',fontsize=size,render_mode=3)
            marker=page.add_rect_annot((r+(-2,-2,2,2)) & page.rect)
            marker.set_info(title='FridayOCR')
            marker.set_flags(fitz.PDF_ANNOT_IS_HIDDEN)
            marker.update()
            count+=1
        if not count:raise InputError('Không nhận được chữ mới. Kiểm tra ngôn ngữ/độ nét hoặc trang đã có lớp chữ.')


def watermark_candidates(entries,sources):
    pages=[];counts={};image_pages=[];image_counts={}
    for entry in entries:
        with document(entry,sources) as doc:
            bs=blocks(doc[0]);pages.append(bs)
            infos=doc[0].get_image_info(hashes=True)
            image_pages.append(infos)
            for key in set(info['digest'].hex() for info in infos):image_counts[key]=image_counts.get(key,0)+1
            for key in set(b['text'].strip() for b in bs):counts[key]=counts.get(key,0)+1
    result=[]
    for index,bs in enumerate(pages):
        items=[]
        for b in bs:
            text=b['text'].strip()
            tilted=abs(b['direction'][1])>.15
            rgb=tuple(int(b['color'][i:i+2],16) for i in (1,3,5))
            light=min(rgb)>130
            repeated=counts.get(text,0)>=2
            if tilted or (light and b['size']>=18) or (repeated and b['size']>=24):
                items.append({'type':'text','bbox':b['bbox'],'text':text,'reason':'Chữ nghiêng / nhạt / lặp lại; cần bạn xác nhận'})
        for image in image_pages[index]:
            if image_counts.get(image['digest'].hex(),0)>=2:
                items.append({'type':'image','bbox':list(image['bbox']),'text':'Ảnh/logo lặp lại trên nhiều trang','reason':'Ảnh lặp lại có thể là watermark; cần xác nhận'})
        result.append({'page':index,'items':items})
    return result
