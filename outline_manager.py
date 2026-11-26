"""Chinese desktop outline manager. Uses Python's bundled tkinter; no server/API."""
from __future__ import annotations
import logging
import os
import queue
import sys
import threading
import traceback
from pathlib import Path
from outline_manager_backend import StateStore,InstanceLock,guess_vehicle,prepare_jobs,run_imports,existing_catalog_status

ROOT=Path(__file__).resolve().parent
TITLE='试验大纲管理 v1.6'
try:
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
except ImportError:
    tk=ttk=filedialog=messagebox=None


def open_local(path):
    if os.name=='nt':os.startfile(str(path))
    else:
        import subprocess
        subprocess.Popen(['xdg-open',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


class OutlineManager:
    def __init__(self,root):
        self.root=root;self.rows=[];self.serial=0;self.busy=False;self.close_when_done=False
        self.events=queue.Queue();self.stop=threading.Event();self.completed=0
        self.store=StateStore(ROOT/'outline_manager_state.json')
        root.title(TITLE);root.geometry('1150x780');root.minsize(920,650)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.report_callback_exception=self.callback_error
        style=ttk.Style(root)
        if 'vista' in style.theme_names():style.theme_use('vista')
        style.configure('Heading.TLabel',font=('Microsoft YaHei UI',17,'bold'))
        main=ttk.Frame(root,padding=18);main.pack(fill='both',expand=True)
        ttk.Label(main,text='试验大纲管理',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(main,text='一次选择多份大纲，确认各自车辆，再批量导入。已导入的大纲会保留，不需要重新从A车开始。').pack(anchor='w',pady=(6,4))
        ttk.Label(main,text='当前工作目录：'+str(ROOT)).pack(anchor='w',pady=(0,10))
        toolbar=ttk.Frame(main);toolbar.pack(fill='x',pady=(0,12))
        self.pick_many=ttk.Button(toolbar,text='批量选择大纲文件',command=self.add_files);self.pick_many.pack(side='left')
        self.add_button=ttk.Button(toolbar,text='添加车辆/完整车号',command=lambda:self.add_row());self.add_button.pack(side='left',padx=8)
        ttk.Button(toolbar,text='查看已导入目录',command=self.open_catalogs).pack(side='left',padx=8)
        ttk.Button(toolbar,text='查看日志',command=self.open_log).pack(side='left',padx=8)
        ttk.Label(main,text='文件名能明确识别车辆时仅预填，仍请检查。不能判断的文件会留空，必须先指定车辆。').pack(anchor='w')
        head=ttk.Frame(main);head.pack(fill='x',pady=(10,3))
        for label,width in [('导入',5),('车辆（A或A204）',18),('大纲文件',62),('状态',23)]:ttk.Label(head,text=label,width=width).pack(side='left',padx=3)
        table=ttk.Frame(main);table.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(table,highlightthickness=0,height=270)
        scroll=ttk.Scrollbar(table,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.inner=ttk.Frame(self.canvas);self.window=self.canvas.create_window((0,0),window=self.inner,anchor='nw')
        self.inner.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.window,width=e.width))
        actions=ttk.Frame(main);actions.pack(fill='x',pady=12)
        self.start_button=ttk.Button(actions,text='开始导入勾选项',command=self.start);self.start_button.pack(side='left')
        self.stop_button=ttk.Button(actions,text='当前文件完成后停止',command=self.request_stop,state='disabled');self.stop_button.pack(side='left',padx=10)
        self.status=tk.StringVar(value='请选择需要导入的大纲。已完成的A/B/C车无需再次勾选。')
        ttk.Label(main,textvariable=self.status,wraplength=1050).pack(anchor='w')
        self.progress=ttk.Progressbar(main,mode='determinate');self.progress.pack(fill='x',pady=8)
        ttk.Label(main,text='处理进度与错误信息').pack(anchor='w')
        self.log=tk.Text(main,height=8,wrap='word',state='disabled');self.log.pack(fill='both',expand=True)
        ttk.Label(main,text='导入完毕后，继续用 run_preview.bat 处理混合车辆记录，再用 run_export.bat 导出。窗口可重新打开；队列和完成结果会保留。',wraplength=1060).pack(anchor='w',pady=(8,0))
        try:restored=self.store.load()
        except Exception:
            logging.exception('Cannot read saved queue');restored=[]
            self.append_log('旧队列无法读取，已重新显示车辆列表；已导入目录不受影响。')
        for row in restored:self.add_row(row['vehicle'],row['path'],row['selected'],save=False)
        existing={r['vehicle'].get().upper() for r in self.rows}
        for vehicle in 'ABCDEF':
            if vehicle not in existing:self.add_row(vehicle,save=False)
        self.root.after(100,self.poll)
    def callback_error(self,kind,value,tb):
        logging.error('GUI callback error',exc_info=(kind,value,tb))
        messagebox.showerror('操作未完成','操作发生错误，详情已保存在logs/outline_manager.log。\n'+str(value),parent=self.root)
    def snapshot(self):
        return [{'id':r['id'],'vehicle':r['vehicle'].get(),'path':r['path'].get(),'selected':r['selected'].get()} for r in self.rows]
    def save(self):
        try:self.store.save(self.snapshot())
        except Exception:logging.exception('Cannot save queue');self.status.set('队列未能保存，请检查C:\\pro是否允许写入。已导入的目录仍保留。')
    def add_row(self,vehicle='',path='',selected=False,save=True):
        if self.busy:return
        self.serial+=1
        row={'id':str(self.serial),'vehicle':tk.StringVar(value=vehicle),'path':tk.StringVar(value=path),'selected':tk.BooleanVar(value=selected)}
        frame=ttk.Frame(self.inner);frame.pack(fill='x',pady=4);row['frame']=frame
        checkbox=ttk.Checkbutton(frame,variable=row['selected'],command=self.save);checkbox.pack(side='left',padx=(3,20))
        code=ttk.Entry(frame,textvariable=row['vehicle'],width=12);code.pack(side='left',padx=3)
        code.bind('<FocusOut>',lambda e,r=row:self.refresh_row(r))
        entry=ttk.Entry(frame,textvariable=row['path'],state='readonly',width=56);entry.pack(side='left',fill='x',expand=True,padx=3)
        choose=ttk.Button(frame,text='选择',width=6,command=lambda r=row:self.pick_file(r));choose.pack(side='left',padx=3)
        row['status']=tk.StringVar(value=existing_catalog_status(ROOT,vehicle))
        ttk.Label(frame,textvariable=row['status'],width=24,wraplength=180).pack(side='left',padx=4)
        remove=ttk.Button(frame,text='移除',width=6,command=lambda r=row:self.remove_row(r));remove.pack(side='left',padx=3)
        row['controls']=[checkbox,code,choose,remove];self.rows.append(row)
        if save:self.save()
        return row
    def refresh_row(self,row):
        if not self.busy:row['status'].set(existing_catalog_status(ROOT,row['vehicle'].get()));self.save()
    def remove_row(self,row):
        if self.busy:return
        row['frame'].destroy();self.rows.remove(row);self.save()
    def choose_dialog(self,multiple=False):
        kwargs={'title':'选择真实试验大纲文件','filetypes':[('支持的大纲','*.pdf *.csv *.tsv *.xlsx *.docx *.txt'),('全部文件','*.*')]}
        return filedialog.askopenfilenames(**kwargs) if multiple else filedialog.askopenfilename(**kwargs)
    def pick_file(self,row):
        if self.busy:return
        path=self.choose_dialog()
        if path:row['path'].set(path);row['selected'].set(True);row['status'].set('待导入，请确认车辆');self.save()
    def add_files(self):
        if self.busy:return
        paths=self.choose_dialog(True);unknown=0
        for path in paths:
            if any(r['path'].get()==path and r['selected'].get() for r in self.rows):continue
            code=guess_vehicle(path)
            row=next((r for r in self.rows if code and r['vehicle'].get().upper()==code and not r['selected'].get()),None)
            if row is None:row=self.add_row(code,save=False)
            row['path'].set(path);row['selected'].set(True);row['status'].set('待导入，请确认车辆')
            if not code:unknown+=1
        self.save()
        if paths:self.status.set(f'已添加{len(paths)}份文件。'+(f'其中{unknown}份未能判断车辆，请填写空白车辆栏。' if unknown else '请确认车辆与文件对应关系，再开始导入。'))
    def append_log(self,text):
        self.log.configure(state='normal');self.log.insert('end',text+'\n');self.log.see('end');self.log.configure(state='disabled')
    def set_busy(self,value):
        self.busy=value;state='disabled' if value else 'normal'
        for button in [self.pick_many,self.add_button,self.start_button]:button.configure(state=state)
        for row in self.rows:
            for control in row['controls']:control.configure(state=state)
        self.stop_button.configure(state='normal' if value else 'disabled')
    def start(self):
        if self.busy:return
        try:jobs=prepare_jobs(self.snapshot())
        except ValueError as exc:messagebox.showwarning('请检查对应关系',str(exc),parent=self.root);return
        for job in jobs:
            row=next(r for r in self.rows if r['id']==job.row_id)
            row['vehicle'].set(job.vehicle)
        self.save();self.completed=0;self.progress.configure(maximum=len(jobs),value=0)
        self.stop.clear();self.set_busy(True);self.status.set(f'开始导入{len(jobs)}份大纲，当前文件处理完后可以安全停止。')
        threading.Thread(target=run_imports,args=(jobs,ROOT,ROOT/'split_experiments.py',self.stop,self.events.put),daemon=True).start()
    def request_stop(self):
        self.stop.set();self.stop_button.configure(state='disabled');self.status.set('当前文件完成后停止。已完成的目录会保留，未完成项可下次继续。')
    def poll(self):
        try:
            while True:
                event=self.events.get_nowait();kind=event['kind']
                row=next((r for r in self.rows if r['id']==event.get('id')),None)
                if kind=='started' and row:
                    row['status'].set('正在导入…');self.status.set('正在整理 '+event['vehicle']+' 车大纲，请稍候。')
                elif kind=='log':
                    text='['+event['vehicle']+'] '+event['text'];self.append_log(text);logging.info(text)
                elif kind in ('success','failure') and row:
                    self.completed+=1;self.progress.configure(value=self.completed)
                    if kind=='success':
                        row['selected'].set(False);row['status'].set(existing_catalog_status(ROOT,event['vehicle']))
                    else:
                        row['status'].set('导入失败，可重试');self.append_log('['+event['vehicle']+'] 失败：'+event.get('text',''));logging.error(event.get('text',''))
                    self.save()
                elif kind=='finished':
                    self.set_busy(False)
                    self.status.set(f"本次成功{event['successes']}份，失败{event['failures']}份。"+('已安全停止，未处理项仍保留。' if event['stopped'] else '已完成项已取消勾选，不会重复导入。'))
                    if self.close_when_done:self.save();self.root.destroy();return
        except queue.Empty:pass
        self.root.after(100,self.poll)
    def open_catalogs(self):
        folder=ROOT/'outlines';folder.mkdir(exist_ok=True)
        try:open_local(folder)
        except Exception as exc:messagebox.showinfo('目录位置',str(folder)+'\n'+str(exc),parent=self.root)
    def open_log(self):
        try:open_local(ROOT/'logs'/'outline_manager.log')
        except Exception:messagebox.showinfo('日志位置',str(ROOT/'logs'/'outline_manager.log'),parent=self.root)
    def close(self):
        if self.busy:
            if messagebox.askyesno('当前仍在处理','是否在当前文件完成后安全关闭？已完成的目录和待办队列都会保留。',parent=self.root):
                self.close_when_done=True;self.request_stop()
            return
        self.save();self.root.destroy()


def main():
    lock=InstanceLock(ROOT/'.outline_manager.lock')
    try:
        (ROOT/'logs').mkdir(exist_ok=True)
        logging.basicConfig(filename=str(ROOT/'logs'/'outline_manager.log'),level=logging.INFO,encoding='utf-8',format='%(asctime)s %(levelname)s %(message)s')
        if not lock.acquire():
            if os.name=='nt':
                import ctypes
                hwnd=ctypes.windll.user32.FindWindowW(None,TITLE)
                if hwnd:ctypes.windll.user32.ShowWindow(hwnd,9);ctypes.windll.user32.SetForegroundWindow(hwnd)
                else:ctypes.windll.user32.MessageBoxW(None,'大纲管理窗口已打开，请查看任务栏。',TITLE,0)
            return 0
        if tk is None:raise RuntimeError('Python缺少tkinter组件。请使用原Python安装程序的Modify功能勾选tcl/tk，再运行本入口。')
        if not (ROOT/'split_experiments.py').is_file():raise RuntimeError('请将全部更新文件合并到原C:\\pro文件夹。')
        logging.info('Starting manager with %s',sys.executable)
        app=tk.Tk();OutlineManager(app);app.mainloop();return 0
    except Exception:
        error=traceback.format_exc()
        try:logging.error(error)
        except Exception:pass
        message='大纲窗口未能启动。请查看或发送 '+str(ROOT/'logs'/'outline_manager.log')+'。\n\n'+error.splitlines()[-1]
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,message,'大纲管理启动失败',16)
        else:print(message,file=sys.stderr)
        return 1
    finally:lock.release()

if __name__=='__main__':raise SystemExit(main())
