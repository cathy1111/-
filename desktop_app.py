"""Offline desktop entry: outline management, preview review, and PDF export."""
import json
import logging
import os
import queue
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from outline_manager_backend import worker_interpreter,InstanceLock

ROOT=Path(__file__).resolve().parent
VERSION='1.6.0'

class DesktopApp:
    def __init__(self,root):
        self.root=root;self.busy=False;self.events=queue.Queue();self.path=tk.StringVar()
        root.title('试验记录智能归档工具 v'+VERSION);root.geometry('960x700');root.minsize(820,580)
        root.protocol('WM_DELETE_WINDOW',self.close)
        frame=ttk.Frame(root,padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='试验记录智能归档工具',font=('Microsoft YaHei UI',19,'bold')).pack(anchor='w')
        ttk.Label(frame,text='本地OCR · 分车大纲 · 先核对后导出 · 运行无需联网').pack(anchor='w',pady=(6,16))
        buttons=ttk.Frame(frame);buttons.pack(fill='x')
        self.outline_button=ttk.Button(buttons,text='① 管理车辆大纲',command=self.outlines);self.outline_button.pack(side='left',padx=4)
        ttk.Button(buttons,text='生成示例资料',command=lambda:self.run('demo')).pack(side='left',padx=4)
        ttk.Button(buttons,text='打开输出目录',command=self.open_out).pack(side='left',padx=4)
        ttk.Label(frame,text='② 选择原始记录PDF（可包含多个车辆）').pack(anchor='w',pady=(22,5))
        row=ttk.Frame(frame);row.pack(fill='x')
        ttk.Entry(row,textvariable=self.path,state='readonly').pack(side='left',fill='x',expand=True)
        self.choose=ttk.Button(row,text='选择PDF',command=self.pick);self.choose.pack(side='left',padx=8)
        actions=ttk.Frame(frame);actions.pack(fill='x',pady=16)
        self.preview=ttk.Button(actions,text='③ 识别并生成预览清单',command=lambda:self.run('preview'));self.preview.pack(side='left',padx=4)
        ttk.Button(actions,text='④ 打开清单核对',command=self.review).pack(side='left',padx=4)
        self.export=ttk.Button(actions,text='⑤ 从核对清单导出PDF',command=lambda:self.run('split'));self.export.pack(side='left',padx=4)
        self.pause_button=ttk.Button(actions,text='暂停识别',command=self.pause,state='disabled');self.pause_button.pack(side='left',padx=4)
        self.status=tk.StringVar(value='先导入各车大纲，再选择PDF并识别；核对清单保存关闭后导出。')
        ttk.Label(frame,textvariable=self.status,wraplength=890).pack(anchor='w',pady=5)
        self.progress=ttk.Progressbar(frame,mode='indeterminate');self.progress.pack(fill='x',pady=8)
        self.log=tk.Text(frame,height=15,wrap='word',state='disabled');self.log.pack(fill='both',expand=True)
        ttk.Label(frame,text='工作目录：'+str(ROOT)).pack(anchor='w',pady=(10,0))
        try:self.path.set(json.loads((ROOT/'desktop_state.json').read_text(encoding='utf-8')).get('pdf',''))
        except (OSError,ValueError):pass
        root.after(100,self.poll)
    def open_file(self,path):
        if os.name=='nt':os.startfile(str(path))
        else:subprocess.Popen(['xdg-open',str(path)])
    def outlines(self):
        exe=Path(worker_interpreter());windowed=exe.with_name('pythonw.exe') if os.name=='nt' else exe
        subprocess.Popen([str(windowed if windowed.exists() else exe),str(ROOT/'outline_manager.py')],cwd=str(ROOT))
    def pick(self):
        value=filedialog.askopenfilename(title='选择原始记录PDF',filetypes=[('PDF','*.pdf')])
        if value:
            self.path.set(value)
            (ROOT/'desktop_state.json').write_text(json.dumps({'pdf':value},ensure_ascii=False),encoding='utf-8')
    def review(self):
        path=ROOT/'out/preview.csv'
        if not path.exists():messagebox.showinfo('尚无清单','请先识别生成预览清单。');return
        self.open_file(path)
    def open_out(self):
        path=ROOT/'out';path.mkdir(exist_ok=True);self.open_file(path)
    def pause(self):
        if self.busy and getattr(self,'task_mode','')=='preview':
            folder=ROOT/'out';folder.mkdir(exist_ok=True)
            (folder/'pause-request').write_text('pause',encoding='ascii')
            self.pause_button.configure(state='disabled');self.status.set('正在等待当前页完成后暂停，进度会保留。')
    def run(self,mode):
        if self.busy:return
        if mode!='demo' and not Path(self.path.get()).is_file():messagebox.showwarning('请选择PDF','请选择现有原始记录PDF。');return
        args=[worker_interpreter(),str(ROOT/'split_experiments.py')]
        if mode=='demo':args+=['make-demo','--out',str(ROOT/'examples/multi_vehicle')]
        else:args+=[mode,'--input',self.path.get(),'--out',str(ROOT/'out'),'--version','V011']
        self.task_mode=mode
        pending=ROOT/'out/pause-request'
        if pending.exists():pending.unlink()
        self.pause_button.configure(state='normal' if mode=='preview' else 'disabled')
        self.busy=True;self.preview.configure(state='disabled');self.export.configure(state='disabled');self.choose.configure(state='disabled');self.outline_button.configure(state='disabled');self.progress.start(15)
        self.status.set('正在处理，请稍候。关闭前请等当前任务完成。')
        def worker():
            try:
                env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
                with subprocess.Popen(args,cwd=str(ROOT),env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0) as proc:
                    for line in proc.stdout:self.events.put(('log',line))
                    code=proc.wait()
                self.events.put(('done',(code,mode)))
            except Exception as exc:self.events.put(('log',str(exc)+'\n'));self.events.put(('done',(1,mode)))
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':
                    self.log.configure(state='normal');self.log.insert('end',value);self.log.see('end');self.log.configure(state='disabled');logging.info(value.rstrip())
                else:
                    self.busy=False;self.progress.stop();self.pause_button.configure(state='disabled')
                    for button in [self.preview,self.export,self.choose,self.outline_button]:button.configure(state='normal')
                    code,mode=value
                    self.status.set('已暂停，已完成页已保存；再次点击③可继续。' if code==2 else '处理失败，请查看上方错误信息。' if code else ('预览已生成：请打开清单核对，保存关闭后再导出。' if mode=='preview' else '处理完成，请打开输出目录或示例目录查看。'))
        except queue.Empty:pass
        self.root.after(100,self.poll)
    def close(self):
        if self.busy:messagebox.showinfo('正在处理','请等当前任务完成后关闭，避免中断数据处理。');return
        self.root.destroy()

def main():
    (ROOT/'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=str(ROOT/'logs/desktop_app.log'),encoding='utf-8',level=logging.INFO)
    lock=InstanceLock(ROOT/'.desktop_app.lock')
    if not lock.acquire():
        if os.name=='nt':
            import ctypes
            h=ctypes.windll.user32.FindWindowW(None,'试验记录智能归档工具 v'+VERSION)
            if h:ctypes.windll.user32.ShowWindow(h,9);ctypes.windll.user32.SetForegroundWindow(h)
        return 0
    try:
        root=tk.Tk();DesktopApp(root);root.mainloop();return 0
    except Exception:
        logging.exception('Desktop startup failed')
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'详情保存在'+str(ROOT/'logs/desktop_app.log'),'软件启动失败',16)
        return 1
    finally:lock.release()

if __name__=='__main__':raise SystemExit(main())

