"""Visual ROI rule editor and local record screening UI (Python 3.8 compatible)."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import uuid
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import fitz
from PIL import Image,ImageTk
from outline_manager_backend import worker_interpreter
from record_audit import validate

ROOT=Path(__file__).resolve().parent
LABELS={'数值填写格式':'numeric','签字栏':'signature','必填栏':'required'}
REVERSE={v:k for k,v in LABELS.items()}

class AuditManager:
    def __init__(self,root):
        self.root=root;self.pdf=None;self.page=0;self.pages=0;self.fields=[];self.pending=None;self.profile_path=None;self.dirty=False;self.busy=False;self.events=queue.Queue();self.ratio=1;self.rotation=0
        root.title('原始记录规范辅助检查');root.geometry(f'{min(1280,root.winfo_screenwidth()-40)}x{min(900,root.winfo_screenheight()-80)}');root.minsize(980,620);root.protocol('WM_DELETE_WINDOW',self.close)
        top=ttk.Frame(root,padding=10);top.pack(fill='x')
        ttk.Button(top,text='选择PDF样张/待检查PDF',command=self.pick_pdf).pack(side='left',padx=3)
        ttk.Button(top,text='上一页',command=lambda:self.turn(-1)).pack(side='left',padx=3)
        ttk.Button(top,text='下一页',command=lambda:self.turn(1)).pack(side='left',padx=3)
        ttk.Button(top,text='载入检查模板',command=self.load_rules).pack(side='left',padx=3)
        ttk.Button(top,text='保存检查模板',command=self.save_rules).pack(side='left',padx=3)
        ttk.Button(top,text='新建模板',command=self.new_rules).pack(side='left',padx=3)
        ttk.Button(top,text='打开示例',command=self.demo).pack(side='left',padx=3)
        self.file_label=ttk.Label(top,text='未选择PDF');self.file_label.pack(side='left',padx=10)
        ttk.Label(root,text='先载入模板，或在样张上拖框设置检查区。只框填写内容，不含“签字/数值”等标签和表格边框。不同版式请建立不同模板。').pack(anchor='w',padx=12)
        content=ttk.Frame(root,padding=10);content.pack(fill='both',expand=True)
        left=ttk.Frame(content);left.pack(side='left',fill='both',expand=True)
        self.canvas=tk.Canvas(left,bg='#d5d5d5',width=700,height=700)
        horizontal=ttk.Scrollbar(left,orient='horizontal',command=self.canvas.xview);self.canvas.configure(xscrollcommand=horizontal.set);horizontal.pack(side='bottom',fill='x')
        scroll=ttk.Scrollbar(left,orient='vertical',command=self.canvas.yview);self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.bind('<ButtonPress-1>',self.begin);self.canvas.bind('<B1-Motion>',self.drag);self.canvas.bind('<ButtonRelease-1>',self.end)
        self.canvas.bind('<MouseWheel>',lambda e:self.canvas.yview_scroll(int(-e.delta/120),'units'))
        right=ttk.Frame(content,width=450);right.pack(side='right',fill='y')
        rule_canvas=tk.Canvas(right,width=430,highlightthickness=0)
        rule_scroll=ttk.Scrollbar(right,orient='vertical',command=rule_canvas.yview);rule_canvas.configure(yscrollcommand=rule_scroll.set)
        rule_scroll.pack(side='right',fill='y');rule_canvas.pack(side='left',fill='both',expand=True)
        side=ttk.Frame(rule_canvas,padding=(12,0));rule_window=rule_canvas.create_window((0,0),window=side,anchor='nw')
        side.bind('<Configure>',lambda e:rule_canvas.configure(scrollregion=rule_canvas.bbox('all')))
        rule_canvas.bind('<Configure>',lambda e:rule_canvas.itemconfigure(rule_window,width=e.width))
        self.name=tk.StringVar(value='新检查模板');self.title=tk.StringVar();self.basis=tk.StringVar();self.example=tk.BooleanVar(value=False)
        for label,var in [('模板名称',self.name),('适用表单标题（建议填写）',self.title),('检查依据/规范条款（必填）',self.basis)]:
            ttk.Label(side,text=label).pack(anchor='w');ttk.Entry(side,textvariable=var,width=48).pack(fill='x',pady=(0,5));var.trace_add('write',self.changed)
        ttk.Checkbutton(side,text='示例规则（不能作为正式检查依据）',variable=self.example,command=self.changed).pack(anchor='w')
        ttk.Separator(side).pack(fill='x',pady=8)
        self.field_name=tk.StringVar();self.kind=tk.StringVar(value='数值填写格式');self.increment=tk.StringVar(value='0.1');self.unit=tk.StringVar();self.device_id=tk.StringVar();self.resolution=tk.StringVar();self.accuracy=tk.StringVar()
        ttk.Label(side,text='框选后填写检查项，再点“添加检查项”').pack(anchor='w')
        for label,var in [('检查项名称（如测量值1/试验员签字）',self.field_name)]:
            ttk.Label(side,text=label).pack(anchor='w');ttk.Entry(side,textvariable=var).pack(fill='x')
        ttk.Combobox(side,textvariable=self.kind,values=list(LABELS),state='readonly').pack(fill='x',pady=5)
        for label,var in [('记录要求的步长（0.1表示1位小数）',self.increment),('单位（与设备信息相同单位）',self.unit),('设备编号',self.device_id),('设备分辨力（数值，不含单位）',self.resolution),('设备准确度/最大允许误差（原文，仅展示）',self.accuracy)]:
            row=ttk.Frame(side);row.pack(fill='x',pady=2);ttk.Label(row,text=label).pack(anchor='w');ttk.Entry(row,textvariable=var).pack(fill='x')
        ttk.Button(side,text='添加检查项（使用刚才框选区域）',command=self.add).pack(fill='x',pady=6)
        self.tree=ttk.Treeview(side,columns=('kind','area'),show='tree headings',height=6);self.tree.heading('#0',text='检查项');self.tree.heading('kind',text='类型');self.tree.heading('area',text='区域')
        self.tree.column('#0',width=145);self.tree.column('kind',width=80);self.tree.column('area',width=100);self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self.highlight)
        ttk.Button(side,text='删除选中项后可重新框选',command=self.remove).pack(fill='x',pady=4)
        ttk.Label(side,text='准确度不等于分辨力；本版不检查检定证书有效性。\n签字仅筛查空白/墨迹，不鉴定签名真伪。',wraplength=420).pack(anchor='w',pady=5)
        bottom=ttk.Frame(root,padding=10);bottom.pack(fill='x')
        self.check_button=ttk.Button(bottom,text='按此模板检查当前PDF全部页面',command=self.check);self.check_button.pack(side='left')
        ttk.Button(bottom,text='打开检查结果目录',command=self.open_results).pack(side='left',padx=10)
        self.status=tk.StringVar(value='初次可点击“打开示例”，载入示例规则和两页扫描记录。');ttk.Label(bottom,textvariable=self.status,wraplength=800).pack(side='left')
        self.log=tk.Text(root,height=4,state='disabled');self.log.pack(fill='x',padx=10,pady=(0,10));root.after(100,self.poll)
    def changed(self,*args):self.dirty=True
    def ask_discard(self):return not self.dirty or messagebox.askyesno('未保存模板','当前模板修改尚未保存，是否放弃这些修改？')
    def pick_pdf(self):
        if self.busy:return
        value=filedialog.askopenfilename(filetypes=[('PDF','*.pdf')])
        if value:
            self.pdf=Path(value).resolve();self.page=0;self.render()
    def render(self):
        try:
            with fitz.open(str(self.pdf)) as doc:
                if doc.needs_pass:raise ValueError('PDF已加密，请使用有权读取的解密副本')
                self.pages=len(doc);page=doc[self.page];self.ratio=page.rect.width/page.rect.height;self.rotation=page.rotation
                pix=page.get_pixmap(matrix=fitz.Matrix(700/page.rect.width,700/page.rect.width),alpha=False)
            self.width=pix.width;self.height=pix.height;self.image=ImageTk.PhotoImage(Image.frombytes('RGB',(pix.width,pix.height),pix.samples))
            self.canvas.delete('all');self.canvas.create_image(0,0,image=self.image,anchor='nw');self.canvas.configure(scrollregion=(0,0,self.width,self.height));self.canvas.yview_moveto(0);self.pending=None
            self.file_label.configure(text=self.pdf.name+f' 第{self.page+1}/{self.pages}页');self.draw_fields()
        except Exception as exc:messagebox.showerror('无法打开PDF',str(exc));self.pdf=None
    def turn(self,delta):
        if not self.pdf or self.busy:return
        self.page=max(0,min(self.pages-1,self.page+delta));self.render()
    def point(self,event):return max(0,min(self.width,self.canvas.canvasx(event.x))),max(0,min(self.height,self.canvas.canvasy(event.y)))
    def begin(self,event):
        if not self.pdf or self.busy:return
        self.start=self.point(event);self.canvas.delete('pending');self.pending=None
    def drag(self,event):
        if not self.pdf or self.busy or not hasattr(self,'start'):return
        x,y=self.point(event);self.canvas.delete('pending');self.canvas.create_rectangle(*self.start,x,y,outline='blue',width=2,tags='pending')
    def end(self,event):
        if not self.pdf or self.busy or not hasattr(self,'start'):return
        x,y=self.point(event);sx,sy=self.start;del self.start
        if abs(x-sx)<8 or abs(y-sy)<6:return
        self.pending=[min(sx,x)/self.width,min(sy,y)/self.height,max(sx,x)/self.width,max(sy,y)/self.height]
        self.status.set('区域已框选，请填写检查项名称/类型后添加。')
    def profile(self):return {'schema':1,'name':self.name.get(),'title_contains':self.title.get(),'basis':self.basis.get(),'example':self.example.get(),'page_ratio':self.template_ratio if hasattr(self,'template_ratio') else self.ratio,'rotation':getattr(self,'template_rotation',self.rotation),'fields':self.fields}
    def add(self):
        if self.busy:return
        if not self.pending:messagebox.showinfo('请先框选','在左侧样张拖框，只框填写区，不含标签或边框。');return
        f={'name':self.field_name.get().strip(),'kind':LABELS[self.kind.get()],'bbox':self.pending,'increment':self.increment.get(),'unit':self.unit.get(),'device_id':self.device_id.get(),'resolution':self.resolution.get(),'accuracy':self.accuracy.get()}
        try:
            profile=self.profile();profile['fields']=self.fields+[f];validate(profile)
        except Exception as exc:messagebox.showwarning('规则未完成',str(exc));return
        if not self.fields:self.template_ratio=self.ratio;self.template_rotation=self.rotation
        self.fields.append(f);self.pending=None;self.canvas.delete('pending');self.dirty=True;self.refresh()
    def refresh(self):
        for i in self.tree.get_children():self.tree.delete(i)
        for i,f in enumerate(self.fields):self.tree.insert('','end',iid=str(i),text=f['name'],values=(REVERSE[f['kind']],','.join(f'{v:.2f}' for v in f['bbox'])))
        self.draw_fields()
    def draw_fields(self):
        self.canvas.delete('field')
        if not self.pdf:return
        for i,f in enumerate(self.fields):
            b=f['bbox'];coords=[b[0]*self.width,b[1]*self.height,b[2]*self.width,b[3]*self.height]
            self.canvas.create_rectangle(*coords,outline='red',width=2,tags='field');self.canvas.create_text(coords[0],coords[1],text=f'{i+1}:{f["name"]}',anchor='sw',fill='red',tags='field')
    def highlight(self,event=None):
        selected=self.tree.selection()
        if selected:
            f=self.fields[int(selected[0])];self.field_name.set(f['name']);self.kind.set(REVERSE[f['kind']])
            for key,var in [('increment',self.increment),('unit',self.unit),('device_id',self.device_id),('resolution',self.resolution),('accuracy',self.accuracy)]:var.set(f.get(key,''))
    def remove(self):
        if self.busy:return
        for i in sorted([int(x) for x in self.tree.selection()],reverse=True):self.fields.pop(i)
        self.dirty=True;self.refresh()
    def new_rules(self):
        if self.busy or not self.ask_discard():return
        self.fields=[];self.name.set('新检查模板');self.title.set('');self.basis.set('');self.example.set(False)
        self.template_ratio=self.ratio;self.template_rotation=self.rotation;self.pending=None;self.profile_path=None;self.dirty=False;self.refresh()
        self.status.set('新模板：选择真实样张，填写规范依据，再框选需要检查的填写区。')
    def load_rules(self,path=None):
        if self.busy or not self.ask_discard():return
        path=path or filedialog.askopenfilename(initialdir=str(ROOT/'audit_rules'),filetypes=[('检查模板JSON','*.json')])
        if not path:return
        try:
            p=validate(json.loads(Path(path).read_text(encoding='utf-8-sig')));self.name.set(p['name']);self.title.set(p.get('title_contains',''));self.basis.set(p['basis']);self.example.set(bool(p.get('example')));self.fields=p['fields'];self.template_ratio=p['page_ratio'];self.template_rotation=p.get('rotation',0);self.profile_path=Path(path);self.dirty=False;self.refresh()
            self.status.set('已载入'+('示例规则：不能用于正式检查。' if p.get('example') else '模板；请确认框线准确落在填写区域。'))
        except Exception as exc:messagebox.showerror('模板加载失败',str(exc))
    def save_rules(self):
        if self.busy:return False
        try:profile=validate(self.profile())
        except Exception as exc:messagebox.showwarning('规则未完成',str(exc));return False
        (ROOT/'audit_rules').mkdir(exist_ok=True)
        path=filedialog.asksaveasfilename(initialdir=str(ROOT/'audit_rules'),defaultextension='.json',filetypes=[('检查模板JSON','*.json')])
        if not path:return False
        Path(path).write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8');self.profile_path=Path(path);self.dirty=False;return True
    def demo(self):
        if self.busy or not self.ask_discard():return
        self.dirty=False;self.pdf=ROOT/'examples/record_audit/规范检查扫描示例.pdf';self.page=0;self.render();self.load_rules(ROOT/'audit_rules/规范检查示例.json')
    def open_results(self):
        folder=ROOT/'out/record_audit';folder.mkdir(exist_ok=True,parents=True)
        os.startfile(str(folder)) if os.name=='nt' else subprocess.Popen(['xdg-open',str(folder)])
    def check(self):
        if self.busy:return
        if not self.pdf:messagebox.showinfo('请选择PDF','请先选择待检查PDF。');return
        try:profile=validate(self.profile())
        except Exception as exc:messagebox.showwarning('规则未完成',str(exc));return
        if not messagebox.askokcancel('检查范围确认',('当前是示例规则，只能测试功能。\n' if profile.get('example') else '')+'请确认所有待检查页面使用相同版式，框线只覆盖填写区域。不同版式需单独检查。\n输出仅为辅助筛查，签字及数值需要人工核对。'):return
        folder=ROOT/'audit_rules';folder.mkdir(exist_ok=True);snapshot=folder/('run_rules_'+uuid.uuid4().hex+'.json');snapshot.write_text(json.dumps(profile,ensure_ascii=False),encoding='utf-8')
        args=[worker_interpreter(),str(ROOT/'record_audit.py'),'--input',str(self.pdf),'--rules',str(snapshot),'--out',str(ROOT/'out/record_audit')]
        self.busy=True;self.check_button.configure(state='disabled');self.status.set('正在检查，请等待。')
        def worker():
            try:
                env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
                with subprocess.Popen(args,cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0) as proc:
                    for line in proc.stdout:self.events.put(('log',line))
                    code=proc.wait()
                self.events.put(('done',code))
            except Exception as exc:self.events.put(('log',str(exc)+'\n'));self.events.put(('done',1))
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':self.log.configure(state='normal');self.log.insert('end',value);self.log.see('end');self.log.configure(state='disabled')
                else:self.busy=False;self.check_button.configure(state='normal');self.status.set('检查失败，请看日志。' if value else '检查完成，请打开检查结果目录中的HTML报告；逐项核对证据图片。')
        except queue.Empty:pass
        self.root.after(100,self.poll)
    def close(self):
        if self.busy:messagebox.showinfo('正在检查','请等待当前检查完成后关闭。');return
        if self.ask_discard():self.root.destroy()

if __name__=='__main__':
    root=tk.Tk();AuditManager(root);root.mainloop()
