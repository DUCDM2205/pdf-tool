const $ = id => document.getElementById(id);
const state = { pages: [], sources: new Map(), selected: null, busy: false, logo: null };
let noticeTimer;

function notice(message) {
  const el = $('notification');
  el.textContent = message; el.classList.add('show');
  clearTimeout(noticeTimer); noticeTimer = setTimeout(() => el.classList.remove('show'), 4300);
}
function selectedPage() { return state.pages.find(p => p.id === state.selected); }
function pagePlan(page) {
  return page.blank ? {blank:true,width:page.width,height:page.height,ops:page.ops,crop:page.crop}
    : {source:page.source,index:page.index,ops:page.ops,crop:page.crop};
}
function allPages() { return state.pages.map(pagePlan); }
function setBusy(busy) { state.busy=busy; refreshControls(); }
function refreshControls() {
  const enabled=!!state.pages.length && !state.busy, hasPage=!!selectedPage() && !state.busy;
  for(const id of ['exportTop','exportSide','splitBtn','imagesBtn','addBlank','convertBtn','extractBtn','reversePages','signDigital']) $(id).disabled=!enabled;
  for(const id of ['removePage','applyCrop','editPage','undoPage','insertFile']) $(id).disabled=!hasPage;
  document.querySelectorAll('.page-action').forEach(el=>el.disabled=!hasPage);
  $('addFile').disabled=state.busy; $('addFileTop').disabled=state.busy;
  $('pageCounter').textContent=`${state.pages.length} trang`;
  $('empty').hidden=state.pages.length>0;
  $('documentTitle').textContent=state.pages.length?'Xem trước và sắp xếp trang':'Tổ chức tài liệu PDF';
  $('documentHint').textContent=state.pages.length?'Kéo các trang để đổi thứ tự. Chọn một trang để xoay, lật hoặc cắt lề.':'Thêm PDF hoặc hình ảnh để xem và sắp xếp từng trang.';
}
async function post(path, payload, binary=false) {
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!response.ok){let message='Không thể xử lý yêu cầu.';try{message=(await response.json()).error||message;}catch{}throw Error(message);}
  return binary?response.blob():response.json();
}
async function uploadFiles(files) {
  if(!files.length)return;
  setBusy(true);
  for(const file of files){
    try{
      const response=await fetch('/api/upload',{method:'POST',headers:{'X-File-Name':encodeURIComponent(file.name)},body:file});
      const data=await response.json();if(!response.ok)throw Error(data.error||'Không tải được file.');
      state.sources.set(data.source,data.name);
      const newPages=data.pages.map(p=>({id:crypto.randomUUID(),source:data.source,index:p.index,ops:[],crop:{left:0,top:0,right:0,bottom:0},width:p.width,height:p.height,name:data.name,preview:null,revision:0}));
      const pos=state.insertAfter?state.pages.findIndex(p=>p.id===state.insertAfter)+1:state.pages.length;state.pages.splice(pos,0,...newPages);if(state.insertAfter)state.insertAfter=newPages.at(-1)?.id;
      if(!state.selected)state.selected=newPages[0]?.id||null;
      drawCards(); await renderPreviews(newPages);
      notice(`Đã thêm ${data.pages.length} trang từ ${data.name}.`);
    }catch(error){notice(`Không thêm được ${file.name}: ${error.message}`);}
  }
  state.insertAfter=null;setBusy(false);
  detectWatermarks();
}
async function renderPreviews(pages){
  // Limit concurrent PDF render jobs on an ordinary laptop.
  const queue=[...pages];
  await Promise.all(Array.from({length:Math.min(3,queue.length)},async()=>{
    while(queue.length){const page=queue.shift();await renderPreview(page);}
  }));
}
async function renderPreview(page){
  const revision=++page.revision;
  try{
    const blob=await post('/api/preview',{page:pagePlan(page)},true);
    if(revision!==page.revision||!state.pages.includes(page))return;
    if(page.preview)URL.revokeObjectURL(page.preview);
    page.preview=URL.createObjectURL(blob);
    const card=document.querySelector(`[data-id="${page.id}"]`);
    if(card){const thumb=card.querySelector('.thumb');thumb.replaceChildren();const img=document.createElement('img');img.src=page.preview;img.alt=`Xem trước ${card.querySelector('b').textContent}`;thumb.append(img);}
  }catch(error){notice(error.message);}
}
function selectPage(id){
  state.selected=id;
  document.querySelectorAll('.page-card').forEach(el=>el.classList.toggle('selected',el.dataset.id===id));
  const page=selectedPage();$('pageProps').hidden=!!page;$('pageForm').hidden=!page;
  if(page){
    const n=state.pages.indexOf(page)+1;
    $('selectedTitle').textContent=`Trang ${n}`;
    $('sourceName').textContent=page.blank?'Trang trắng':`${page.name} · trang ${page.index+1}`;
    for(const side of ['Left','Top','Right','Bottom'])$(`crop${side}`).value=page.crop[side.toLowerCase()]||0;
  }
  refreshControls();
}
function drawCards(){
  const grid=$('grid');grid.replaceChildren();
  state.pages.forEach((page,index)=>{
    const card=document.createElement('button');card.type='button';card.className='page-card'+(page.id===state.selected?' selected':'');card.dataset.id=page.id;card.draggable=true;
    const thumb=document.createElement('div');thumb.className='thumb';
    if(page.preview){const img=document.createElement('img');img.src=page.preview;img.alt=`Xem trước trang ${index+1}`;thumb.append(img);}
    else {const loading=document.createElement('span');loading.className='loading';loading.textContent='Đang tạo xem trước…';thumb.append(loading);}
    const caption=document.createElement('div');caption.className='page-caption';
    const label=document.createElement('b');label.textContent=`Trang ${index+1}`;
    const source=document.createElement('small');source.textContent=page.blank?'Trang trắng':page.name;source.title=source.textContent;
    const grab=document.createElement('span');grab.className='grab';grab.textContent='⠿';grab.title='Kéo để đổi thứ tự';
    caption.append(label,source,grab);card.append(thumb,caption);
    card.onclick=()=>selectPage(page.id);
    card.ondragstart=e=>{if(state.busy){e.preventDefault();return;}e.dataTransfer.setData('text/plain',page.id);e.dataTransfer.effectAllowed='move';card.classList.add('dragging');};
    card.ondragend=()=>{card.classList.remove('dragging');document.querySelectorAll('.drag-over').forEach(el=>el.classList.remove('drag-over'));};
    card.ondragover=e=>{e.preventDefault();card.classList.add('drag-over');};
    card.ondragleave=()=>card.classList.remove('drag-over');
    card.ondrop=e=>{e.preventDefault();card.classList.remove('drag-over');const from=state.pages.findIndex(p=>p.id===e.dataTransfer.getData('text/plain'));
      const to=state.pages.indexOf(page);if(from<0||to<0||from===to)return;const [moved]=state.pages.splice(from,1);state.pages.splice(to,0,moved);drawCards();selectPage(moved.id);notice('Đã đổi thứ tự trang.');};
    grid.append(card);
  });
  selectPage(state.selected);
}
function download(blob,name){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
async function exportPDF(){
  if(!state.pages.length||state.busy)return;
  setBusy(true);
  try{
    const decoration=decorationOptions();
    const file=await post('/api/export',{pages:allPages(),decoration},true);
    download(file,'Friday-PDF-edited.pdf');notice('Đã xuất file PDF mới.');
  }catch(error){notice(error.message);}finally{setBusy(false);}
}
async function splitPDF(){
  if(!state.pages.length||state.busy)return;
  try{const file=await post('/api/split',{pages:allPages(),ranges:$('splitRanges').value,decoration:decorationOptions()},true);download(file,'Friday-PDF-split.zip');$('splitDialog').close();notice('Đã xuất các phần PDF trong file ZIP.');}
  catch(error){notice(error.message);}
}
for(const id of ['addFile','addFileTop','emptyAdd'])$(id).onclick=()=>$('fileInput').click();
$('fileInput').onchange=e=>{uploadFiles([...e.target.files]);e.target.value='';};
for(const id of ['exportTop','exportSide'])$(id).onclick=exportPDF;
$('addBlank').onclick=()=>{const current=selectedPage();const page={id:crypto.randomUUID(),blank:true,width:595,height:842,ops:[],crop:{left:0,top:0,right:0,bottom:0},name:'Trang trắng',preview:null,revision:0};state.pages.splice(current?state.pages.indexOf(current)+1:state.pages.length,0,page);drawCards();selectPage(page.id);renderPreview(page);notice('Đã chèn trang trắng sau trang đang chọn.');};
$('removePage').onclick=()=>{const index=state.pages.findIndex(p=>p.id===state.selected);if(index<0)return;const [removed]=state.pages.splice(index,1);if(removed.preview)URL.revokeObjectURL(removed.preview);state.selected=state.pages[Math.min(index,state.pages.length-1)]?.id||null;drawCards();notice('Đã xóa trang khỏi bản đang chỉnh sửa.');};
document.querySelectorAll('.page-action').forEach(button=>button.onclick=()=>{const page=selectedPage();if(!page)return;const action=button.dataset.action;page.ops=action==='reset'?[]:[...page.ops,action];renderPreview(page);notice('Đã cập nhật hướng trang đang chọn.');});
$('applyCrop').onclick=()=>{const page=selectedPage();if(!page)return;const crop=Object.fromEntries(['left','top','right','bottom'].map(s=>[s,Number($(`crop${s[0].toUpperCase()+s.slice(1)}`).value)]));
  if(Object.values(crop).some(n=>!Number.isFinite(n)||n<0||n>40)){notice('Mỗi lề cắt phải từ 0 đến 40%.');return;}
  page.crop=crop;renderPreview(page);notice('Đã cập nhật vùng cắt của trang.');};
$('splitBtn').onclick=()=>{const count=state.pages.length;$('splitRanges').value=count>1?`1-${Math.ceil(count/2)}, ${Math.ceil(count/2)+1}-${count}`:'1';$('splitDialog').showModal();};
$('confirmSplit').onclick=e=>{e.preventDefault();splitPDF();};
$('imagesBtn').onclick=async()=>{const format=window.prompt('Xuất ảnh dạng PNG hay JPG?', 'PNG');if(!format)return;const type=format.trim().toLowerCase();if(!['png','jpg','jpeg'].includes(type)){notice('Chọn PNG hoặc JPG.');return;}setBusy(true);try{const file=await post('/api/images',{pages:allPages(),type:type==='jpeg'?'jpg':type,decoration:decorationOptions()},true);download(file,'Friday-PDF-images.zip');notice('Đã xuất ảnh từng trang trong file ZIP.');}catch(error){notice(error.message);}finally{setBusy(false);}};
$('watermarkLogo').onchange=e=>{const file=e.target.files[0];if(!file){state.logo=null;return;}if(file.size>5*1024*1024){notice('Logo cần nhỏ hơn 5 MB.');e.target.value='';return;}const reader=new FileReader();reader.onload=()=>{state.logo=reader.result;notice('Đã chọn logo watermark.');};reader.readAsDataURL(file);};
refreshControls();

function decorationOptions(){return {header:$('headerText').value,footer:$('footerText').value,replaceHeaders:$('replaceHeaders').checked,numberPages:$('pageNumbers').checked,watermark:{text:$('watermarkText').value,logo:state.logo,opacity:$('opacity').value,angle:$('angle').value}};}
function readData(file){return new Promise((resolve,reject)=>{if(!file)return reject(Error('Chọn file trước.'));const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Không đọc được file.'));reader.readAsDataURL(file);});}
async function detectWatermarks(){
  if(!state.pages.length)return;
  const pages=[...state.pages];
  try{const result=await post('/api/watermarks',{pages:pages.map(pagePlan)});result.pages.forEach(p=>{if(state.pages.includes(pages[p.page]))pages[p.page].watermarks=p.items;});const count=result.pages.reduce((n,p)=>n+p.items.length,0);if(count)notice(`Phát hiện ${count} vùng nghi là watermark. Mở sửa trang → Xóa watermark để kiểm tra; chưa xóa gì.`);}catch(error){notice('Quét watermark: '+error.message);}
}
$('insertFile').onclick=()=>{state.insertAfter=state.selected;$('fileInput').click();};
$('fileInput').addEventListener('cancel',()=>{state.insertAfter=null;});
for(const id of ['addFile','addFileTop','emptyAdd'])$(id).onclick=()=>{state.insertAfter=null;$('fileInput').click();};
$('reversePages').onclick=()=>{state.pages.reverse();drawCards();notice('Đã đảo thứ tự trang.');};
$('extractBtn').onclick=async()=>{const range=prompt('Các trang cần trích xuất (ví dụ 1-3,5):','1');if(!range)return;try{const indices=[];for(const part of range.split(',')){const m=part.trim().match(/^(\d+)(?:-(\d+))?$/);if(!m)throw Error('Khoảng trang không hợp lệ.');const a=+m[1],b=+(m[2]||m[1]);if(a<1||b<a||b>state.pages.length)throw Error('Khoảng trang vượt tài liệu.');for(let i=a;i<=b;i++)indices.push(i-1);}download(await post('/api/export',{pages:indices.map(i=>pagePlan(state.pages[i])),decoration:decorationOptions()},true),'Friday-extracted.pdf');}catch(e){notice(e.message);}};
$('convertBtn').onclick=async()=>{$('convertDialog').showModal();try{const c=await (await fetch('/api/capabilities')).json();$('dependencyStatus').textContent=`Office → PDF: ${c.office?'sẵn sàng':'cần cài LibreOffice'} · OCR: ${c.ocr?'sẵn sàng':'cần cài Tesseract'} · Word: ${c.word?'sẵn sàng':'cần cài requirements.txt'}. Chi tiết xem INSTALL.md.`;}catch{}};
$('runConvert').onclick=async()=>{const button=$('runConvert');button.disabled=true;setBusy(true);try{const target=$('convertTarget').value;download(await post('/api/convert',{pages:allPages(),target,mode:$('pptMode').value,decoration:decorationOptions()},true),'Friday-converted.'+target);notice('Đã chuyển đổi. Hãy kiểm tra bố cục và số liệu trong file xuất.');}catch(e){notice(e.message);$('dependencyStatus').textContent=e.message;}finally{button.disabled=false;setBusy(false);}};
$('signDigital').onclick=()=>$('certificateDialog').showModal();
$('runSign').onclick=async()=>{const button=$('runSign');button.disabled=true;setBusy(true);try{const certificate=await readData($('certFile').files[0]);const password=$('certPassword').value;download(await post('/api/sign',{pages:allPages(),decoration:decorationOptions(),certificate,password},true),'Friday-signed.pdf');$('certificateDialog').close();notice('Đã ký và xuất PDF.');}catch(e){notice(e.message);}finally{$('certPassword').value='';$('certFile').value='';button.disabled=false;setBusy(false);}};
$('certificateDialog').addEventListener('close',()=>{$('certPassword').value='';$('certFile').value='';});

const editor={page:null,scan:null,mode:'text',item:null,rect:null,image:null,rows:[['',''],['','']],busy:false,previewURL:null};
function setEditorBusy(value){editor.busy=value;$('editorDialog').querySelectorAll('button,input,select,textarea').forEach(el=>el.disabled=value);}
function editorError(e){$('editorError').textContent=e?.message||e||'';}
function snapshot(page){return {...pagePlan(page),width:page.width,height:page.height,name:page.name};}
function remember(page){page.history??=[];page.history.push(snapshot(page));if(page.history.length>25)page.history.shift();}
async function undoPage(page){if(!page?.history?.length){notice('Chưa có thao tác để hoàn tác.');return;}const old=page.history.pop();delete page.blank;delete page.source;delete page.index;Object.assign(page,old);await renderPreview(page);if($('editorDialog').open)await loadEditor();notice('Đã hoàn tác sửa nội dung.');}
$('undoPage').onclick=()=>undoPage(selectedPage());$('undoInEditor').onclick=()=>undoPage(editor.page);
$('editPage').onclick=async()=>{editor.page=selectedPage();if(!editor.page)return;$('editorDialog').showModal();await loadEditor();};
$('editorClose').onclick=()=>{if(!editor.busy)$('editorDialog').close();};
$('editorDialog').addEventListener('cancel',e=>{if(editor.busy)e.preventDefault();});
async function loadEditor(){setEditorBusy(true);editorError('');try{editor.scan=await post('/api/scan',{page:pagePlan(editor.page)});await detectWatermarks();$('editorImage').src=editor.scan.preview;$('editorStatus').textContent=`Trang ${state.pages.indexOf(editor.page)+1} · ${editor.scan.text.length} vùng chữ · ${editor.scan.images.length} ảnh · ${editor.scan.tables.length} bảng`;setMode(editor.mode);}catch(e){editorError(e);}finally{setEditorBusy(false);}}
const hints={text:'Chọn đoạn chữ trên trang. Font gốc được nhận diện; đoạn thay thế dùng DejaVu Sans có tiếng Việt. Bố cục ngoài vùng sửa được giữ nguyên.',addText:'Kéo vùng trống trên trang rồi nhập chữ. Vùng chữ phải đủ lớn để xuống dòng.',image:'Bấm ảnh để thay, xóa, cắt hoặc di chuyển. Kéo khung để đổi vị trí/kích thước; chữ xung quanh giữ nguyên.',addImage:'Tải ảnh, rồi kéo khung trên trang đến vị trí mong muốn.',signature:'Tải ảnh hoặc vẽ chữ ký, rồi kéo khung đến ô ký. Đây là chữ ký hình ảnh.',table:'Bấm bảng được nhận diện để sửa số liệu/hàng/cột. Bảng không nhận diện được có thể tạo bằng vùng mới.',form:'Chọn trường có sẵn hoặc ô trống/dòng chấm được phát hiện, nhập dữ liệu rồi áp dụng. Có thể vẽ thêm trường mới.',redact:'Kéo vùng thông tin cần xóa. Khi áp dụng, nội dung trong vùng được loại khỏi bản xuất và bôi đen. Hãy kiểm tra vùng kỹ trước khi xuất.',watermark:'Chỉ xóa mục bạn đánh dấu. Nhận diện tự động có thể nhầm logo hoặc tiêu đề.',ocr:'Nhận diện chữ trong ảnh scan. Cần Tesseract và gói ngôn ngữ tương ứng. Kết quả cần kiểm tra lại.'};
function setMode(mode){if(editor.scan)$('editorImage').src=editor.scan.preview;editor.mode=mode;editor.item=null;editor.image=null;editor.rect=null;$('allowImageOverlap').checked=false;editorError('');$('editImageFile').value='';$('editText').value='';$('deleteImage').checked=false;$('imageCrop').value='0,0,0,0';$('modeHint').textContent=hints[mode];$('editorTools').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
  $('textControls').hidden=!['text','addText','form','table'].includes(mode);$('imageControls').hidden=!['image','addImage','signature'].includes(mode);$('signatureControls').hidden=mode!=='signature';$('tableControls').hidden=mode!=='table';$('ocrControls').hidden=mode!=='ocr';$('watermarkControls').hidden=mode!=='watermark';$('geometryControls').hidden=['watermark','ocr'].includes(mode);$('objectSelect').parentElement.hidden=['watermark','ocr','addText','addImage','signature','redact'].includes(mode);$('placementImage').hidden=true;
  if(mode==='table'){editor.rows=[['',''],['','']];drawTable();}
  if(mode==='watermark')drawWatermarks();
  drawObjects();drawSelection();
  if(editor.scan&&['addText','addImage','signature','table','form','redact'].includes(mode))setRect([30,30,Math.min(250,editor.scan.width-10),Math.min(110,editor.scan.height-10)]);
}
$('editorTools').querySelectorAll('button').forEach(b=>b.onclick=()=>setMode(b.dataset.mode));
function objects(){const s=editor.scan;if(!s)return[];if(editor.mode==='text')return s.text;if(editor.mode==='image')return s.images;if(editor.mode==='table')return s.tables;if(editor.mode==='form')return [...s.forms,...s.formCandidates.map((f,i)=>({...f,id:'candidate-'+i}))];return[];}
function position(el,r){const s=editor.scan;el.style.left=r[0]/s.width*100+'%';el.style.top=r[1]/s.height*100+'%';el.style.width=(r[2]-r[0])/s.width*100+'%';el.style.height=(r[3]-r[1])/s.height*100+'%';}
function drawObjects(){const layer=$('objectLayer');layer.replaceChildren();const select=$('objectSelect');select.replaceChildren(new Option('Chọn trên trang',''));objects().forEach((item,i)=>{const label=(item.text||item.name||item.reason||`Đối tượng ${i+1}`).slice(0,90);select.add(new Option(label,String(i)));const button=document.createElement('button');button.type='button';button.className='object-hit';button.title=label;button.setAttribute('aria-label',label);position(button,item.bbox);button.onclick=e=>{e.stopPropagation();chooseObject(item,i);};layer.append(button);});}
$('objectSelect').onchange=e=>{if(e.target.value!=='')chooseObject(objects()[Number(e.target.value)],Number(e.target.value));};
function chooseObject(item,index){$('editorImage').src=editor.scan.preview;editor.item=item;editor.image=null;$('placementImage').hidden=true;$('objectSelect').value=String(index);setRect([...item.bbox]);$('editText').value=item.text??item.value??'';$('editSize').value=Math.round((item.size||11)*10)/10;$('editColor').value=item.color||'#182538';$('editBold').checked=!!item.bold;$('editItalic').checked=!!item.italic;$('fontInfo').textContent=item.font?`Font gốc: ${item.font}. Đoạn mới: DejaVu Sans Unicode.`:'Font Unicode DejaVu Sans';if(editor.mode==='table'){editor.rows=item.rows.map(r=>r.map(v=>v||''));drawTable();}editorError('');}
function setRect(r){editor.rect=r;for(const [id,v] of [['editX',r[0]],['editY',r[1]],['editW',r[2]-r[0]],['editH',r[3]-r[1]]])$(id).value=Math.round(v*10)/10;drawSelection();}
function drawSelection(){const box=$('selectionBox');box.hidden=!editor.rect;if(editor.rect)position(box,editor.rect);}
for(const id of ['editX','editY','editW','editH'])$(id).oninput=()=>{const x=+$('editX').value,y=+$('editY').value,w=+$('editW').value,h=+$('editH').value;editor.rect=[x,y,x+w,y+h];drawSelection();};
let drag=null;
function point(event){const r=$('editorStage').getBoundingClientRect();return [Math.max(0,Math.min(editor.scan.width,(event.clientX-r.left)/r.width*editor.scan.width)),Math.max(0,Math.min(editor.scan.height,(event.clientY-r.top)/r.height*editor.scan.height))];}
$('editorStage').onpointerdown=e=>{if(editor.busy||!editor.scan||['watermark','ocr'].includes(editor.mode)||e.target.closest('.object-hit'))return;const start=point(e);drag={start,original:editor.rect?[...editor.rect]:null,type:e.target.classList.contains('resize-handle')?'resize':e.target.closest('#selectionBox')?'move':'draw'};if(drag.type==='draw')setRect([...start,start[0]+1,start[1]+1]);$('editorStage').setPointerCapture(e.pointerId);e.preventDefault();};
$('editorStage').onpointermove=e=>{if(!drag)return;const p=point(e),dx=p[0]-drag.start[0],dy=p[1]-drag.start[1],r=drag.original;if(drag.type==='draw')setRect([Math.min(p[0],drag.start[0]),Math.min(p[1],drag.start[1]),Math.max(p[0],drag.start[0]),Math.max(p[1],drag.start[1])]);else if(drag.type==='resize')setRect([r[0],r[1],Math.max(r[0]+2,p[0]),Math.max(r[1]+2,p[1])]);else{const w=r[2]-r[0],h=r[3]-r[1],x=Math.max(0,Math.min(editor.scan.width-w,r[0]+dx)),y=Math.max(0,Math.min(editor.scan.height-h,r[1]+dy));setRect([x,y,x+w,y+h]);}};
$('editorStage').onpointerup=()=>{drag=null;};$('editorStage').onpointercancel=()=>{drag=null;};
$('editImageFile').onchange=async e=>{try{const file=e.target.files[0];if(file.size>10*1024*1024)throw Error('Ảnh tối đa 10 MB.');editor.image=await readData(file);showPlacement();}catch(e){editorError(e);}};
function showPlacement(){$('placementImage').src=editor.image;$('placementImage').hidden=!editor.image;}
function drawTable(){const host=$('tableGrid');host.replaceChildren();const table=document.createElement('table');editor.rows.forEach((row,i)=>{const tr=table.insertRow();row.forEach((value,j)=>{const input=document.createElement('input');input.value=value;input.setAttribute('aria-label',`Hàng ${i+1} cột ${j+1}`);input.oninput=()=>editor.rows[i][j]=input.value;tr.insertCell().append(input);});});host.append(table);}
$('addRow').onclick=()=>{editor.rows.push(Array(editor.rows[0].length).fill(''));drawTable();};$('removeRow').onclick=()=>{if(editor.rows.length>1)editor.rows.pop();drawTable();};$('addCol').onclick=()=>{editor.rows.forEach(r=>r.push(''));drawTable();};$('removeCol').onclick=()=>{if(editor.rows[0].length>1)editor.rows.forEach(r=>r.pop());drawTable();};
function drawWatermarks(){const list=$('watermarkList');list.replaceChildren();const items=editor.page.watermarks||[];if(!items.length){list.textContent='Chưa phát hiện watermark dạng chữ trên trang này. Có thể dùng Sửa ảnh để chọn logo.';return;}items.forEach((item,i)=>{const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.value=i;label.append(check,document.createTextNode(' '+item.text));list.append(label);});}
function operation(){const mode=editor.mode,op={kind:mode,bbox:editor.rect,text:$('editText').value,size:+$('editSize').value,family:$('editFamily').value,color:$('editColor').value,bold:$('editBold').checked,italic:$('editItalic').checked,allowImageOverlap:$('allowImageOverlap').checked};
  if(['text','image'].includes(mode)&&!editor.item)throw Error('Chọn chữ hoặc ảnh trên trang trước.');
  if(editor.item&&!String(editor.item.id).startsWith('candidate-'))op.id=editor.item.id;
  if(['image','addImage','signature'].includes(mode)){op.image=editor.image;op.delete=$('deleteImage').checked;op.keepRatio=$('keepRatio').checked;op.crop=$('imageCrop').value.split(',').map(Number);if(op.crop.length!==4||op.crop.some(n=>!Number.isFinite(n)))throw Error('Lề ảnh cần 4 số: trái,trên,phải,dưới.');}
  if(mode==='table')op.rows=editor.rows;
  if(mode==='ocr')op.language=$('ocrLanguage').value;
  if(mode==='watermark'){op.kind='removeWatermark';op.items=[...$('watermarkList').querySelectorAll('input:checked')].map(c=>editor.page.watermarks[+c.value]);if(!op.items.length)throw Error('Chọn watermark cần xóa.');}
  return op;
}
$('previewEdit').onclick=async()=>{setEditorBusy(true);editorError('');try{const blob=await post('/api/edit-preview',{page:pagePlan(editor.page),operation:operation()},true);if(editor.previewURL)URL.revokeObjectURL(editor.previewURL);editor.previewURL=URL.createObjectURL(blob);$('editorImage').src=editor.previewURL;$('editorStatus').textContent='Đang xem thử — chưa áp dụng. Bấm Áp dụng để lưu vào trang.';}catch(e){editorError(e);}finally{setEditorBusy(false);}};
$('applyEdit').onclick=async()=>{let op;try{op=operation();}catch(e){editorError(e);return;}if(op.kind==='redact'&&!confirm('Xóa nội dung trong vùng khỏi bản PDF xuất và bôi đen?'))return;setEditorBusy(true);editorError('');try{const result=await post('/api/edit',{page:pagePlan(editor.page),operation:op});remember(editor.page);delete editor.page.blank;Object.assign(editor.page,{source:result.source,index:0,ops:[],crop:{},width:result.pages[0].width,height:result.pages[0].height,watermarks:[]});await renderPreview(editor.page);await loadEditor();notice('Đã áp dụng. Bạn có thể hoàn tác trước khi xuất.');}catch(e){editorError(e);}finally{setEditorBusy(false);}};
const signatureCanvas=$('signatureCanvas'),signatureContext=signatureCanvas.getContext('2d');let signing=false;
function signaturePoint(e){const r=signatureCanvas.getBoundingClientRect();return[(e.clientX-r.left)*signatureCanvas.width/r.width,(e.clientY-r.top)*signatureCanvas.height/r.height];}
signatureCanvas.onpointerdown=e=>{signing=true;signatureCanvas.setPointerCapture(e.pointerId);signatureContext.beginPath();signatureContext.moveTo(...signaturePoint(e));};signatureCanvas.onpointermove=e=>{if(!signing)return;signatureContext.strokeStyle='#162536';signatureContext.lineWidth=3;signatureContext.lineCap='round';signatureContext.lineTo(...signaturePoint(e));signatureContext.stroke();};signatureCanvas.onpointerup=()=>{signing=false;};signatureCanvas.onpointercancel=()=>{signing=false;};
$('clearSignature').onclick=()=>signatureContext.clearRect(0,0,500,160);$('useSignature').onclick=()=>{editor.image=signatureCanvas.toDataURL('image/png');showPlacement();};
$('saveSignature').onclick=()=>{if(!editor.image){editorError('Tải ảnh hoặc bấm Dùng nét vẽ trước.');return;}try{localStorage.setItem('friday-signature',editor.image);notice('Đã lưu chữ ký trong trình duyệt này.');}catch{editorError('Không đủ dung lượng lưu chữ ký.');}};
$('loadSignature').onclick=()=>{editor.image=localStorage.getItem('friday-signature');if(!editor.image)editorError('Chưa lưu chữ ký.');showPlacement();};$('forgetSignature').onclick=()=>{localStorage.removeItem('friday-signature');notice('Đã xóa chữ ký đã lưu.');};
