"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Archive, ArrowDown, ArrowRight, ArrowUp, BookMarked, BookOpenText, BrainCircuit, Check, ChevronDown,
  ChevronRight, Circle, Clock3, FileText, Flame, FolderTree, GraduationCap, Highlighter,
  GripVertical, Library, LoaderCircle, Menu, MessageSquareText, NotebookPen, Plus, Quote, RefreshCw,
  Search, Send, Settings, ShieldCheck, Sparkles, Star, Target, Upload, WandSparkles, X,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Assessment, Chapter, ChatAnswer, Citation, Dashboard, Doc, Exam, Note, OutlineProposal, Point, ProposalNode, Review, Subject } from "@/lib/types";

type View = "dashboard" | "curriculum" | "library" | "study" | "assessment" | "notes" | "review" | "settings";
type Toast = { message: string; tone: "ok" | "error" } | null;

const nav: { id: View; label: string; icon: typeof BookOpenText }[] = [
  { id: "dashboard", label: "今日研习", icon: BookOpenText },
  { id: "curriculum", label: "课程目录", icon: FolderTree },
  { id: "library", label: "资料库", icon: Library },
  { id: "study", label: "AI 研讨", icon: MessageSquareText },
  { id: "assessment", label: "诊断测验", icon: GraduationCap },
  { id: "notes", label: "笔记簿", icon: NotebookPen },
  { id: "review", label: "复习队列", icon: BrainCircuit },
];

const statusLabel: Record<string, string> = { not_started: "未开始", learning: "学习中", reviewing: "待复习", mastered: "已掌握" };
const questionTypeLabel: Record<string, string> = { short_answer: "简答题" };

export default function Home() {
  const [view, setView] = useState<View>("dashboard");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [exams, setExams] = useState<Exam[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [reviews, setReviews] = useState<Review[]>([]);
  const [selectedSubject, setSelectedSubject] = useState<number | undefined>();
  const [selectedChapter, setSelectedChapter] = useState<number | undefined>();
  const [resumeConversation, setResumeConversation] = useState<number | undefined>();
  const [reader, setReader] = useState<{ citation: Citation; content: string } | null>(null);
  const [toast, setToast] = useState<Toast>(null);
  const [loading, setLoading] = useState(true);

  const flash = useCallback((message: string, tone: "ok" | "error" = "ok") => {
    setToast({ message, tone }); window.setTimeout(() => setToast(null), 3200);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [tree, documents, dash, noteRows, reviewRows] = await Promise.all([
        api<Exam[]>("/api/curriculum"), api<Doc[]>("/api/documents"), api<Dashboard>(`/api/dashboard${selectedSubject ? `?subject_id=${selectedSubject}` : ""}`),
        api<Note[]>("/api/notes"), api<Review[]>("/api/reviews/today"),
      ]);
      setExams(tree); setDocs(documents); setDashboard(dash); setNotes(noteRows); setReviews(reviewRows);
      if (!selectedSubject && tree[0]?.subjects[0]) setSelectedSubject(tree[0].subjects[0].id);
    } catch (error) { flash(error instanceof Error ? error.message : "无法连接服务", "error"); }
    finally { setLoading(false); }
  }, [flash, selectedSubject]);

  useEffect(() => { refresh(); }, [refresh]);

  const subject = useMemo(() => exams.flatMap(e => e.subjects).find(s => s.id === selectedSubject), [exams, selectedSubject]);
  const chapter = useMemo(() => subject?.chapters.find(c => c.id === selectedChapter), [subject, selectedChapter]);

  async function openCitation(citation: Citation) {
    try {
      const data = await api<{ chunks: { content: string }[] }>(`/api/documents/${citation.document_id}/chunks?locator=${encodeURIComponent(citation.locator)}`);
      setReader({ citation, content: data.chunks.map(item => item.content).join("\n\n") || citation.quote });
    } catch (error) {
      if (error instanceof Error && error.message.includes("资料不存在")) {
        setReader({ citation, content: `${citation.quote}\n\n（原资料已删除，以上为回答生成时保存的引用快照。）` });
        flash("原资料已删除，正在显示历史引用快照", "error");
      } else {
        flash(error instanceof Error ? error.message : "原文暂时不可用", "error");
      }
    }
  }

  function go(next: View) { setView(next); setMobileOpen(false); }
  function resumeStudy() {
    const recent = dashboard?.recent_session;
    if (recent?.subject_id) setSelectedSubject(recent.subject_id);
    setSelectedChapter(recent?.chapter_id);
    setResumeConversation(recent?.context.conversation_id);
    go("study");
  }

  return (
    <main className="app-shell">
      <div className="grain" />
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
        <button className="mobile-close" onClick={() => setMobileOpen(false)} aria-label="关闭菜单"><X /></button>
        <div className="brand" onClick={() => go("dashboard")}>
          <div className="brand-seal">砚</div>
          <div><strong>砚台</strong><span>财务学习工作台</span></div>
        </div>
        <div className="nav-caption">研习路径</div>
        <nav>
          {nav.map(item => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => go(item.id)}><item.icon size={19} /><span>{item.label}</span>{item.id === "review" && reviews.length > 0 && <b>{reviews.length}</b>}</button>)}
        </nav>
        <div className="sidebar-foot">
          <div className="focus-card"><Target size={18} /><div><span>当前目标</span><strong>{subject?.name || "选择学习科目"}</strong></div><small>{dashboard?.progress ?? 0}%</small></div>
          <button className={view === "settings" ? "settings active" : "settings"} onClick={() => go("settings")}><Settings size={18} />系统设置</button>
          <div className="grounded"><ShieldCheck size={15} />仅依据你的资料回答</div>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <button className="menu-button" onClick={() => setMobileOpen(true)}><Menu /></button>
          <div className="crumb"><span>学习台</span><ChevronRight size={14} /><strong>{nav.find(n => n.id === view)?.label || "设置"}</strong></div>
          <div className="top-actions"><button className="icon-button" onClick={refresh} title="刷新"><RefreshCw size={17} className={loading ? "spin" : ""} /></button><div className="date-stamp"><span>{new Date().toLocaleDateString("zh-CN", { month: "long", day: "numeric" })}</span><b>{new Date().toLocaleDateString("zh-CN", { weekday: "short" })}</b></div></div>
        </header>

        <div className="page-wrap" key={view}>
          {view === "dashboard" && <DashboardView data={dashboard} notes={notes} docs={docs} onGo={go} onResume={resumeStudy} />}
          {view === "curriculum" && <CurriculumView exams={exams} onRefresh={refresh} flash={flash} onStudy={(s, c) => { setSelectedSubject(s); setSelectedChapter(c); setResumeConversation(undefined); go("study"); }} onReview={async pointId => { try { await api(`/api/reviews/from-point/${pointId}`, { method: "POST" }); await refresh(); go("review"); } catch (e) { flash((e as Error).message, "error"); } }} />}
          {view === "library" && <LibraryView docs={docs} exams={exams} onRefresh={refresh} flash={flash} />}
          {view === "study" && <StudyView exams={exams} subject={subject} chapter={chapter} subjectId={selectedSubject} chapterId={selectedChapter} initialConversationId={resumeConversation} setSubject={setSelectedSubject} setChapter={setSelectedChapter} onCitation={openCitation} flash={flash} />}
          {view === "assessment" && <AssessmentView subjectId={selectedSubject} chapterId={selectedChapter} onCitation={openCitation} flash={flash} />}
          {view === "notes" && <NotesView notes={notes} onRefresh={refresh} flash={flash} />}
          {view === "review" && <ReviewView reviews={reviews} onRefresh={refresh} flash={flash} />}
          {view === "settings" && <SettingsView flash={flash} />}
        </div>
      </section>
      {reader && <ReaderDrawer reader={reader} onClose={() => setReader(null)} />}
      {toast && <div className={`toast ${toast.tone}`}><span>{toast.tone === "ok" ? <Check size={17} /> : <X size={17} />}</span>{toast.message}</div>}
    </main>
  );
}

function PageTitle({ eyebrow, title, copy, action }: { eyebrow: string; title: string; copy: string; action?: React.ReactNode }) {
  return <div className="page-title"><div><span>{eyebrow}</span><h1>{title}</h1><p>{copy}</p></div>{action}</div>;
}

function DashboardView({ data, notes, docs, onGo, onResume }: { data: Dashboard | null; notes: Note[]; docs: Doc[]; onGo: (view: View) => void; onResume: () => void }) {
  return <>
    <PageTitle eyebrow="GOOD MORNING · 今日计划" title="把零散知识，磨成你的判断力。" copy="从上次停下的地方继续。所有进度来自真实学习记录。" action={<button className="primary" onClick={onResume}>继续研习 <ArrowRight size={17} /></button>} />
    <div className="metric-grid">
      <article className="metric hero-metric"><div className="metric-icon"><Flame /></div><span>连续研习</span><strong>{data?.streak ?? 0}<small> 天</small></strong><p>今天完成一次研习即可续上记录</p></article>
      <article className="metric"><span>今日待复习</span><strong>{data?.review_due ?? 0}<small> 项</small></strong><button onClick={() => onGo("review")}>进入队列 <ArrowRight size={14} /></button></article>
      <article className="metric"><span>已入库资料</span><strong>{data?.documents ?? 0}<small> 份</small></strong><button onClick={() => onGo("library")}>管理资料 <ArrowRight size={14} /></button></article>
      <article className="metric"><span>整体掌握度</span><strong>{data?.progress ?? 0}<small>%</small></strong><div className="progress"><i style={{ width: `${data?.progress ?? 0}%` }} /></div></article>
    </div>
    <div className="dashboard-grid">
      <article className="paper-card continue-card">
        <div className="card-head"><div><span className="kicker">CONTINUE</span><h2>续上你的学习现场</h2></div><Clock3 size={20} /></div>
        <div className="study-ticket"><div className="ticket-index">01</div><div><span>最近学习</span><h3>{data?.recent_session ? "恢复上次研习现场" : "从一门科目开始"}</h3><p>{data?.recent_session ? "你的会话、资料范围和章节位置都已保存。" : "选择科目并上传资料，建立第一段可追踪的学习记录。"}</p></div><button onClick={onResume}><ArrowRight /></button></div>
      </article>
      <article className="paper-card weak-card"><div className="card-head"><div><span className="kicker red">FOCUS</span><h2>薄弱知识点</h2></div><Highlighter size={20} /></div><div className="weak-list">{data?.weak_points?.slice(0, 4).map((point, i) => <div key={point.id}><b>0{i + 1}</b><span>{point.name}</span><em>{Math.round(point.mastery)}%</em></div>) || <p className="empty">完成诊断后显示薄弱项</p>}</div></article>
    </div>
    <div className="dashboard-grid lower">
      <article className="paper-card"><div className="card-head"><div><span className="kicker">RECENT NOTES</span><h2>最近笔记</h2></div><NotebookPen size={19} /></div>{notes.slice(0, 3).map(note => <div className="note-row" key={note.id}><Star size={14} fill={note.favorite ? "currentColor" : "none"} /><div><strong>{note.title}</strong><span>{note.content.slice(0, 48) || "空白笔记"}</span></div></div>)}{notes.length === 0 && <button className="empty-action" onClick={() => onGo("notes")}><Plus />写下第一条笔记</button>}</article>
      <article className="paper-card"><div className="card-head"><div><span className="kicker">SOURCE STATUS</span><h2>资料可信状态</h2></div><ShieldCheck size={19} /></div><div className="source-summary"><div className="source-ring"><strong>{docs.filter(d => d.status === "ready").length}</strong><span>可检索</span></div><p>AI 只能看到已成功解析、并与当前科目绑定的资料。证据不足时将严格拒答。</p></div></article>
    </div>
  </>;
}

function CurriculumView({ exams, onRefresh, flash, onStudy, onReview }: { exams: Exam[]; onRefresh: () => void; flash: (m: string, t?: "ok" | "error") => void; onStudy: (s: number, c: number) => void; onReview: (pointId: number) => void }) {
  const [openExam, setOpenExam] = useState<number | null>(exams[0]?.id ?? null);
  const [openSubject, setOpenSubject] = useState<number | null>(null);
  const [newName, setNewName] = useState("");
  async function addChapter(subjectId: number) { if (!newName.trim()) return; try { await api("/api/curriculum/chapters", { method: "POST", body: JSON.stringify({ parent_id: subjectId, name: newName }) }); setNewName(""); onRefresh(); flash("章节已加入目录"); } catch (e) { flash((e as Error).message, "error"); } }
  return <><PageTitle eyebrow="CURRICULUM · 可编辑知识树" title="课程目录" copy="考试、科目、章节、知识点各司其职。资料可以换，学习路径不能乱。" />
    <div className="curriculum-layout"><div className="tree-panel">{exams.map(exam => <section key={exam.id} className="exam-block"><button className="exam-title" onClick={() => setOpenExam(openExam === exam.id ? null : exam.id)}><span className="exam-code">{exam.code}</span><div><strong>{exam.name}</strong><small>{exam.subjects.length} 门科目</small></div>{openExam === exam.id ? <ChevronDown /> : <ChevronRight />}</button>{openExam === exam.id && <div className="subject-list">{exam.subjects.map(sub => <div key={sub.id} className="subject-node"><button onClick={() => setOpenSubject(openSubject === sub.id ? null : sub.id)}><BookMarked size={17} /><span>{sub.name}</span><em>{sub.chapters.length}章</em>{openSubject === sub.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</button>{openSubject === sub.id && <div className="chapter-list">{sub.chapters.map(ch => <div className="chapter-node" key={ch.id}><div><span>{String(ch.position + 1).padStart(2, "0")}</span><strong>{ch.name}</strong><button onClick={() => onStudy(sub.id, ch.id)}>研习</button></div>{ch.points.map(p => <div className="point-node" key={p.id}><Circle size={9} fill={p.status === "mastered" ? "currentColor" : "none"} /><span>{p.name}</span><small>{statusLabel[p.status]}</small><div><i style={{ width: `${p.mastery}%` }} /></div><button className="point-review" onClick={() => onReview(p.id)}>加入复习</button></div>)}</div>)}<div className="inline-add"><input value={newName} onChange={e => setNewName(e.target.value)} placeholder="新增章节名称" /><button onClick={() => addChapter(sub.id)}><Plus size={15} /></button></div></div>}</div>)}</div>}</section>)}</div>
      <aside className="method-panel"><span className="kicker red">LEARNING LOGIC</span><h2>不是看完，<br />才叫学会。</h2><p>知识点掌握度由有据研讨和复习表现推进，不能手动点亮。</p><ol><li><b>01</b> 上传并绑定资料</li><li><b>02</b> 核对自动目录</li><li><b>03</b> 进入苏格拉底研讨</li><li><b>04</b> 按复习队列巩固</li></ol></aside>
    </div></>;
}

function LibraryView({ docs, exams, onRefresh, flash }: { docs: Doc[]; exams: Exam[]; onRefresh: () => void; flash: (m: string, t?: "ok" | "error") => void }) {
  const fileRef = useRef<HTMLInputElement>(null); const [uploading, setUploading] = useState(false); const [subject, setSubject] = useState(exams[0]?.subjects[0]?.id || 0); const [outline, setOutline] = useState<OutlineProposal | null>(null); const [outlineDoc, setOutlineDoc] = useState<Doc | null>(null);
  async function upload(file?: File) { if (!file) return; if (!subject) { flash("请先选择资料所属科目", "error"); return; } setUploading(true); const form = new FormData(); form.append("file", file); form.append("subject_id", String(subject)); try { const uploaded = await api<Doc>("/api/documents", { method: "POST", body: form }); flash("资料已解析，正在自动拆解课程目录"); onRefresh(); await openOutline(uploaded); } catch (e) { flash((e as Error).message, "error"); } finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; } }
  async function remove(doc: Doc) { if (!window.confirm(`删除《${doc.name}》？历史引用会标记为来源不可用。`)) return; try { await api(`/api/documents/${doc.id}?confirm=true`, { method: "DELETE" }); onRefresh(); flash("资料已删除"); } catch (e) { flash((e as Error).message, "error"); } }
  async function openOutline(doc: Doc) { try { const result = await api<OutlineProposal>(`/api/documents/${doc.id}/outline`); setOutlineDoc(doc); setOutline(result); } catch (e) { flash((e as Error).message, "error"); } }
  useEffect(() => { if (!outlineDoc || !outline || !["extracting", "enhancing"].includes(outline.status)) return; const timer = window.setTimeout(() => openOutline(outlineDoc), 1400); return () => window.clearTimeout(timer); }, [outline, outlineDoc]);
  const outlineLabel: Record<string, string> = { waiting: "等待拆解", extracting: "识别目录", enhancing: "AI 补全", review: "待确认", confirmed: "已加入课程", failed: "拆解失败" };
  return <><PageTitle eyebrow="SOURCE LIBRARY · 证据仓" title="资料库" copy="上传教材、讲义与法规。只有解析成功的文字资料才会进入 AI 检索。" action={<><input ref={fileRef} type="file" hidden accept=".pdf,.docx,.txt,.md,.markdown" onChange={e => upload(e.target.files?.[0])} /><button className="primary" onClick={() => fileRef.current?.click()} disabled={uploading}>{uploading ? <LoaderCircle className="spin" /> : <Upload />}上传资料</button></>} />
    <div className="upload-strip"><div><WandSparkles /><span><strong>上传后自动拆解学习目录</strong><small>先识别原目录，再用 AI 补全知识点；确认前绝不修改正式课程</small></span></div><label>绑定科目<select value={subject} onChange={e => setSubject(Number(e.target.value))}>{exams.flatMap(e => e.subjects).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label></div>
    <div className="document-table"><div className="table-head"><span>资料名称</span><span>绑定范围</span><span>目录状态</span><span>入库时间</span><span /></div>{docs.map(doc => <div className="doc-row" key={doc.id}><div className="doc-name"><FileText /><span><strong>{doc.name}</strong><small>{doc.original_name}</small></span></div><span>{exams.flatMap(e => e.subjects).find(s => s.id === doc.subject_id)?.name || "未绑定"}</span><button className={`outline-state ${doc.outline_status}`} onClick={() => openOutline(doc)}><i className={`status ${doc.outline_status}`} />{outlineLabel[doc.outline_status] || doc.outline_status}{["extracting", "enhancing"].includes(doc.outline_status) && <LoaderCircle className="spin" />}</button><span>{new Date(doc.created_at).toLocaleDateString("zh-CN")}</span><div className="doc-actions"><button onClick={() => openOutline(doc)} title="查看目录"><FolderTree size={17} /></button><button onClick={() => remove(doc)} title="删除"><Archive size={17} /></button></div></div>)}{docs.length === 0 && <div className="table-empty"><Library /><strong>资料库还是空的</strong><span>上传第一份资料，AI 才有资格开口。</span></div>}</div>
    {outline && outlineDoc && <OutlineStudio document={outlineDoc} initial={outline} onClose={() => { setOutline(null); setOutlineDoc(null); onRefresh(); }} onChange={setOutline} flash={flash} />}
  </>;
}

function OutlineStudio({ document, initial, onClose, onChange, flash }: { document: Doc; initial: OutlineProposal; onClose: () => void; onChange: (p: OutlineProposal) => void; flash: (m: string, t?: "ok" | "error") => void }) {
  const [draft, setDraft] = useState(initial); const [busy, setBusy] = useState(false); const [source, setSource] = useState<{ locator: string; content: string } | null>(null); const [dragIndex, setDragIndex] = useState<number | null>(null);
  useEffect(() => setDraft(initial), [initial]);
  function changeChapter(index: number, patch: Partial<ProposalNode>) { setDraft(value => ({ ...value, nodes: value.nodes.map((node, i) => i === index ? { ...node, ...patch } : node) })); }
  function changePoint(chapterIndex: number, pointIndex: number, patch: Partial<ProposalNode>) { setDraft(value => ({ ...value, nodes: value.nodes.map((chapter, i) => i === chapterIndex ? { ...chapter, children: (chapter.children || []).map((point, j) => j === pointIndex ? { ...point, ...patch } : point) } : chapter) })); }
  function reorder(from: number, to: number) { if (from === to) return; setDraft(value => { const nodes = [...value.nodes]; const [moved] = nodes.splice(from, 1); nodes.splice(to, 0, moved); return { ...value, nodes: nodes.map((node, position) => ({ ...node, position })) }; }); }
  function addChapter() { setDraft(value => ({ ...value, nodes: [...value.nodes, { id: 0, node_type: "chapter", title: "新章节", original_title: "新章节", position: value.nodes.length, confidence: .5, source_chunk_ids: [], source_locators: [], action: "create", children: [] }] })); }
  function addPoint(chapterIndex: number) { if (!draft.nodes[chapterIndex].id) { flash("先保存新章节，再拆分知识点", "error"); return; } setDraft(value => ({ ...value, nodes: value.nodes.map((chapter, i) => i === chapterIndex ? { ...chapter, children: [...(chapter.children || []), { id: 0, node_type: "point", title: "新知识点", original_title: "新知识点", position: chapter.children?.length || 0, confidence: .5, source_chunk_ids: chapter.source_chunk_ids, source_locators: chapter.source_locators, action: "create" }] } : chapter) })); }
  async function save() { setBusy(true); try { const nodes = draft.nodes.flatMap(chapter => [{ id: chapter.id || undefined, node_type: "chapter", title: chapter.title, position: chapter.position, parent_id: null, action: chapter.action, target_node_id: chapter.target_node_id || null, source_chunk_ids: chapter.source_chunk_ids, source_locators: chapter.source_locators }, ...(chapter.children || []).map(point => ({ id: point.id || undefined, node_type: "point", title: point.title, position: point.position, parent_id: chapter.id || null, action: point.action, target_node_id: point.target_node_id || null, source_chunk_ids: point.source_chunk_ids, source_locators: point.source_locators }))]); const result = await api<OutlineProposal>(`/api/outline-proposals/${draft.id}`, { method: "PATCH", body: JSON.stringify({ nodes }) }); setDraft(result); onChange(result); flash("目录草稿已保存"); return result; } catch (e) { flash((e as Error).message, "error"); return null; } finally { setBusy(false); } }
  async function confirm() { setBusy(true); try { const saved = await save(); if (!saved) return; await api(`/api/outline-proposals/${saved.id}/confirm`, { method: "POST" }); flash("目录已写入正式课程树"); onClose(); } catch (e) { flash((e as Error).message, "error"); } finally { setBusy(false); } }
  async function retry() { setBusy(true); try { await api(`/api/outline-proposals/${draft.id}/retry`, { method: "POST" }); const next = { ...draft, status: "extracting", error: undefined }; setDraft(next); onChange(next); flash("正在重新生成目录"); } catch (e) { flash((e as Error).message, "error"); } finally { setBusy(false); } }
  async function showSource(node: ProposalNode) { const locator = node.source_locators[0]; if (!locator) { flash("该手工节点尚未绑定原文", "error"); return; } try { const data = await api<{ chunks: { content: string }[] }>(`/api/documents/${document.id}/chunks?locator=${encodeURIComponent(locator)}`); setSource({ locator, content: data.chunks.map(x => x.content).join("\n\n") }); } catch (e) { flash((e as Error).message, "error"); } }
  const working = ["extracting", "enhancing"].includes(draft.status);
  return <div className="outline-scrim"><section className="outline-studio"><header><div className="outline-brand"><span><WandSparkles /></span><div><small>CURRICULUM PROPOSAL</small><strong>{document.name}</strong></div></div><div className="outline-head-actions"><em className={`proposal-status ${draft.status}`}>{working && <LoaderCircle className="spin" />}{draft.status === "extracting" ? "识别原目录" : draft.status === "enhancing" ? "AI 补全知识点" : draft.status === "review" ? "等待你的确认" : draft.status === "confirmed" ? "已写入课程" : "生成失败"}</em><button onClick={onClose}><X /></button></div></header>
      {working ? <div className="outline-working"><div className="scan-orbit"><WandSparkles /></div><h2>{draft.status === "extracting" ? "正在识别资料结构" : "正在整理学习知识点"}</h2><p>正式课程树不会在这个阶段发生任何变化。</p><div className="scan-line" /></div> : draft.status === "failed" ? <div className="outline-failed"><AlertTriangle /><h2>目录生成失败</h2><p>{draft.error}</p><button className="primary" onClick={retry} disabled={busy}><RefreshCw />重新生成</button></div> : <>
        <div className="outline-summary"><div><span>识别结果</span><strong>{draft.result_summary.chapters || draft.nodes.length}<small> 章</small></strong></div><div><span>知识点</span><strong>{draft.result_summary.points || draft.nodes.reduce((n, x) => n + (x.children?.length || 0), 0)}<small> 个</small></strong></div><div><span>建议合并</span><strong>{draft.result_summary.merge_suggestions || 0}<small> 项</small></strong></div><div className="ai-badge"><ShieldCheck /><p><strong>{draft.ai_enhanced ? "DeepSeek 已增强" : "规则目录"}</strong><span>{draft.ai_enhanced ? "所有节点均带来源" : "未使用模型扩写"}</span></p></div></div>
        {draft.warning && <div className="outline-warning"><AlertTriangle />{draft.warning}<button onClick={retry}>重新增强</button></div>}
        <div className="outline-body"><div className="outline-tree"><div className="tree-toolbar"><div><span>拖动章节排序，修改结果只保存在草稿</span><b>置信度低于 60% 的节点需要重点核对</b></div><button onClick={addChapter}><Plus />新增章节</button></div>{draft.nodes.map((chapter, chapterIndex) => <article className={`proposal-chapter ${chapter.action === "ignore" ? "ignored" : ""}`} key={`${chapter.id}-${chapterIndex}`} draggable onDragStart={() => setDragIndex(chapterIndex)} onDragOver={e => e.preventDefault()} onDrop={() => { if (dragIndex !== null) reorder(dragIndex, chapterIndex); setDragIndex(null); }}><div className="proposal-chapter-head"><GripVertical /><span className="chapter-number">{String(chapterIndex + 1).padStart(2, "0")}</span><input value={chapter.title} onChange={e => changeChapter(chapterIndex, { title: e.target.value })} /><Confidence value={chapter.confidence} /><select value={chapter.action} onChange={e => changeChapter(chapterIndex, { action: e.target.value as ProposalNode["action"] })}><option value="create">新增</option><option value="merge">合并 #{chapter.target_node_id || "?"}</option><option value="ignore">忽略</option></select><button onClick={() => showSource(chapter)} title="查看原文"><BookOpenText /></button></div><div className="proposal-points">{chapter.children?.map((point, pointIndex) => <div className={`proposal-point ${point.action === "ignore" ? "ignored" : ""}`} key={`${point.id}-${pointIndex}`}><Circle /><input value={point.title} onChange={e => changePoint(chapterIndex, pointIndex, { title: e.target.value })} /><Confidence value={point.confidence} /><select value={point.action} onChange={e => changePoint(chapterIndex, pointIndex, { action: e.target.value as ProposalNode["action"] })}><option value="create">新增</option><option value="merge">合并 #{point.target_node_id || "?"}</option><option value="ignore">忽略</option></select><button onClick={() => showSource(point)}><BookOpenText /></button></div>)}<button className="add-point" onClick={() => addPoint(chapterIndex)}><Plus />拆出一个知识点</button></div></article>)}</div>
          <aside className={`outline-source ${source ? "open" : ""}`}><div><span>来源核对</span>{source && <button onClick={() => setSource(null)}><X /></button>}</div>{source ? <><strong>{source.locator}</strong><p>{source.content}</p></> : <div className="source-placeholder"><BookOpenText /><p>点击任一节点后的原文按钮，在这里核对它为什么被拆成这一章。</p></div>}</aside></div>
        <footer><div><ShieldCheck /><span>确认前不会修改课程、掌握度、笔记或复习记录</span></div><div><button className="secondary" onClick={onClose}>稍后处理</button><button className="secondary" onClick={save} disabled={busy}>{busy && <LoaderCircle className="spin" />}保存草稿</button><button className="primary" onClick={confirm} disabled={busy || draft.status === "confirmed"}><Check />确认写入课程</button></div></footer>
      </>}
    </section></div>;
}

function Confidence({ value }: { value: number }) { const percent = Math.round(value * 100); return <span className={`confidence ${percent < 60 ? "low" : percent < 80 ? "medium" : "high"}`}>{percent}%</span>; }

function StudyView({ exams, subject, chapter, subjectId, chapterId, initialConversationId, setSubject, setChapter, onCitation, flash }: { exams: Exam[]; subject?: Subject; chapter?: Chapter; subjectId?: number; chapterId?: number; initialConversationId?: number; setSubject: (id: number) => void; setChapter: (id?: number) => void; onCitation: (c: Citation) => void; flash: (m: string, t?: "ok" | "error") => void }) {
  const [question, setQuestion] = useState(""); const [mode, setMode] = useState("answer"); const [asking, setAsking] = useState(false); const [conversationId, setConversationId] = useState<number>(); const [messages, setMessages] = useState<{ role: string; text: string; answer?: ChatAnswer }[]>([]); const loadedConversation = useRef<number | undefined>(undefined); const draftLoaded = useRef(false);
  useEffect(() => { setQuestion(window.localStorage.getItem("study-question-draft") || ""); draftLoaded.current = true; }, []);
  useEffect(() => { if (draftLoaded.current) window.localStorage.setItem("study-question-draft", question); }, [question]);
  useEffect(() => {
    if (!initialConversationId || loadedConversation.current === initialConversationId) return;
    loadedConversation.current = initialConversationId;
    api<{ id: number; mode: string; summary?: string; messages: { role: string; content: string; payload?: ChatAnswer }[] }>(`/api/conversations/${initialConversationId}`)
      .then(saved => { setConversationId(saved.id); setMode(saved.mode); setMessages(saved.messages.map(message => ({ role: message.role, text: message.content, answer: message.role === "assistant" ? message.payload : undefined }))); })
      .catch(error => flash(error instanceof Error ? error.message : "无法恢复会话", "error"));
  }, [initialConversationId, flash]);
  async function ask() { if (!question.trim() || asking) return; const prompt = question; setQuestion(""); setMessages(m => [...m, { role: "user", text: prompt }]); setAsking(true); try { const pageContext = { view: "study", subject: subject?.name || "", chapter: chapter?.name || "全部章节", subject_id: subjectId ?? null, chapter_id: chapterId ?? null }; const result = await api<ChatAnswer>("/api/ai/ask", { method: "POST", body: JSON.stringify({ question: prompt, conversation_id: conversationId, subject_id: subjectId, chapter_id: chapterId, mode, page_context: pageContext }) }); setConversationId(result.conversation_id); setMessages(m => [...m, { role: "assistant", text: result.answer, answer: result }]); await api("/api/sessions", { method: "POST", body: JSON.stringify({ subject_id: subjectId, chapter_id: chapterId, route: "study", context: { conversation_id: result.conversation_id, page: pageContext } }) }); } catch (e) { flash((e as Error).message, "error"); setMessages(m => [...m, { role: "error", text: (e as Error).message }]); } finally { setAsking(false); } }
  return <><PageTitle eyebrow="GROUNDED STUDY · 有据研讨" title="AI 研讨室" copy="先限定科目与章节，再提问。回答中的每个关键结论都能回到原文。" />
    <div className="study-layout"><aside className="context-rail"><span className="kicker">STUDY SCOPE</span><h3>本次研习范围</h3><label>科目<select value={subjectId} onChange={e => { setSubject(Number(e.target.value)); setChapter(undefined); }}>{exams.flatMap(e => e.subjects).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label><label>章节<select value={chapterId || ""} onChange={e => setChapter(e.target.value ? Number(e.target.value) : undefined)}><option value="">全部章节</option>{subject?.chapters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><div className="scope-rule"><ShieldCheck /><p><strong>严格资料约束</strong><span>没有依据，宁可拒答。</span></p></div><div className="study-modes"><button className={mode === "answer" ? "active" : ""} onClick={() => setMode("answer")}><Sparkles />精讲模式</button><button className={mode === "socratic" ? "active" : ""} onClick={() => setMode("socratic")}><BrainCircuit />苏格拉底</button></div></aside>
      <section className="chat-paper"><div className="chat-head"><div><span>{subject?.name || "选择科目"}</span><strong>{chapter?.name || "全科资料研讨"}</strong></div><div className="live-dot"><i />证据检索已启用</div></div><div className="messages">{messages.length === 0 && <div className="chat-welcome"><div className="ink-orbit"><Quote /></div><span>从一个真正困住你的问题开始</span><h2>“为什么递延所得税资产<br />不能想当然地确认？”</h2><div>{["解释一个概念", "比较两个处理方法", "用反例检验理解"].map(x => <button key={x} onClick={() => setQuestion(x)}>{x}</button>)}</div></div>}{messages.map((m, i) => <div key={i} className={`message ${m.role}`}><span className="role">{m.role === "user" ? "我" : m.role === "assistant" ? "砚台" : "!"}</span><div><p>{m.text}</p>{m.answer?.grounded === false && <div className="insufficient"><ShieldCheck />资料证据不足，未使用模型常识补答</div>}{m.answer?.citations && m.answer.citations.length > 0 && <div className="citation-list"><span>引用依据</span>{m.answer.citations.map(c => <button key={c.chunk_id} onClick={() => onCitation(c)}><b>C{c.chunk_id}</b><span>{c.document_name} · {c.locator}</span><ChevronRight /></button>)}</div>}{m.answer?.follow_up_questions?.map(q => <button key={q} className="follow-up" onClick={() => setQuestion(q)}>{q}<ArrowRight /></button>)}</div></div>)}{asking && <div className="message assistant thinking"><span className="role">砚台</span><div><LoaderCircle className="spin" /><p>正在检索证据并核对引用…</p></div></div>}</div><div className="composer"><textarea value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }} placeholder={mode === "socratic" ? "说说你目前是怎么理解的…" : "基于当前资料提问，Enter 发送…"} /><button onClick={ask} disabled={!question.trim() || asking}><Send /></button><span>AI 可能出错，但无引用的答案不会被放行。</span></div></section>
    </div></>;
}

function AssessmentView({ subjectId, chapterId, onCitation, flash }: { subjectId?: number; chapterId?: number; onCitation: (c: Citation) => void; flash: (m: string, t?: "ok" | "error") => void }) {
  const [assessment, setAssessment] = useState<Assessment | null>(null); const [answers, setAnswers] = useState<Record<number, string>>({}); const [scores, setScores] = useState<Record<number, number>>({}); const [busy, setBusy] = useState(false);
  async function create() { if (!subjectId) return flash("请先在课程或研讨页选择科目", "error"); setBusy(true); try { const row = await api<{ id: number }>("/api/assessments", { method: "POST", body: JSON.stringify({ subject_id: subjectId, chapter_id: chapterId, question_count: 5 }) }); setAssessment(await api<Assessment>(`/api/assessments/${row.id}`)); } catch (e) { flash((e as Error).message, "error"); } finally { setBusy(false); } }
  async function submit(questionId: number) { try { const result = await api<{ score: number }>(`/api/assessments/${assessment?.id}/attempts`, { method: "POST", body: JSON.stringify({ question_id: questionId, response: answers[questionId] || "", self_rating: 3, duration_seconds: 0 }) }); setScores(value => ({ ...value, [questionId]: result.score })); flash("作答已记录并更新掌握度"); } catch (e) { flash((e as Error).message, "error"); } }
  return <><PageTitle eyebrow="DIAGNOSTIC · 有据诊断" title="章节诊断" copy="每道题都来自已绑定资料，答错后直接进入复习闭环。" action={<button className="primary" disabled={busy} onClick={create}>{busy && <LoaderCircle className="spin" />}生成诊断</button>} /><div className="assessment-list">{assessment?.questions.map((question, index) => <article className="paper-card" key={question.id}><span className="kicker">QUESTION {index + 1} · {questionTypeLabel[question.type] || question.type}</span><h2>{question.prompt}</h2><textarea value={answers[question.id] || ""} onChange={e => setAnswers(value => ({ ...value, [question.id]: e.target.value }))} placeholder="写下你的答案" /><div><button className="primary" onClick={() => submit(question.id)}>提交答案</button>{scores[question.id] !== undefined && <strong>得分 {Math.round(scores[question.id] * 100)}%</strong>}</div>{scores[question.id] !== undefined && <section><p>{question.explanation}</p>{question.citations.map(c => <button key={c.chunk_id} onClick={() => onCitation(c)}>{c.document_name} · {c.locator}</button>)}</section>}</article>)}{!assessment && <div className="table-empty"><GraduationCap /><strong>尚未生成诊断</strong><span>先确认资料目录，再开始章节诊断。</span></div>}</div></>;
}

function NotesView({ notes, onRefresh, flash }: { notes: Note[]; onRefresh: () => void; flash: (m: string, t?: "ok" | "error") => void }) {
  const [selected, setSelected] = useState<Note | null>(notes[0] || null); const [title, setTitle] = useState(""); const [content, setContent] = useState(""); const [search, setSearch] = useState(""); const saving = useRef(false);
  useEffect(() => { if (selected) { setTitle(selected.title); setContent(selected.content); } }, [selected]);
  const shown = notes.filter(n => `${n.title}${n.content}`.includes(search));
  async function save() { if (!title.trim() || saving.current) return; saving.current = true; const body = { title, content, tags: selected?.tags || [], favorite: selected?.favorite || false }; try { const saved = selected ? await api<Note>(`/api/notes/${selected.id}`, { method: "PUT", body: JSON.stringify(body) }) : await api<Note>("/api/notes", { method: "POST", body: JSON.stringify(body) }); setSelected(saved); flash("笔记已存档"); await onRefresh(); } catch (e) { flash((e as Error).message, "error"); } finally { saving.current = false; } }
  function fresh() { setSelected(null); setTitle("未命名笔记"); setContent(""); }
  return <><PageTitle eyebrow="NOTEBOOK · 双向笔记" title="笔记簿" copy="把结论、疑问和原文证据放在一起，别让笔记沦为复制粘贴坟场。" action={<button className="primary" onClick={fresh}><Plus />新建笔记</button>} /><div className="notes-layout"><aside className="note-index"><div className="searchbox"><Search /><input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索笔记" /></div>{shown.map(note => <button key={note.id} className={selected?.id === note.id ? "active" : ""} onClick={() => setSelected(note)}><div><strong>{note.title}</strong>{note.favorite && <Star size={13} fill="currentColor" />}</div><p>{note.content.slice(0, 55) || "空白笔记"}</p><span>{new Date(note.updated_at).toLocaleDateString("zh-CN")}</span></button>)}{shown.length === 0 && <div className="mini-empty">没有匹配的笔记</div>}</aside><section className="note-editor"><div className="editor-tools"><span>MARKDOWN</span><div><button onClick={() => setContent(c => c + "\n## 小结\n")}>H2</button><button onClick={() => setContent(c => c + "\n- 要点\n")}>•</button><button onClick={save} className="save-note">保存</button></div></div><input className="note-title-input" value={title} onChange={e => setTitle(e.target.value)} placeholder="笔记标题" /><textarea value={content} onChange={e => setContent(e.target.value)} onBlur={() => title && save()} placeholder="写下你的理解、疑问和证据…\n\n支持 Markdown。离开编辑框时自动保存。" /><div className="editor-foot"><span><Clock3 />自动保存已启用</span><span>{content.length} 字</span></div></section></div></>;
}

function ReviewView({ reviews, onRefresh, flash }: { reviews: Review[]; onRefresh: () => void; flash: (m: string, t?: "ok" | "error") => void }) {
  const [index, setIndex] = useState(0); const [revealed, setRevealed] = useState(false); const item = reviews[index];
  async function grade(quality: number) { if (!item) return; try { await api(`/api/reviews/${item.id}/complete`, { method: "POST", body: JSON.stringify({ quality }) }); flash("复习结果已记录"); setRevealed(false); if (index >= reviews.length - 1) { setIndex(0); onRefresh(); } else setIndex(i => i + 1); } catch (e) { flash((e as Error).message, "error"); } }
  return <><PageTitle eyebrow="RECALL QUEUE · 主动回忆" title="今日复习" copy="先回忆，再看答案。复习间隔根据你的真实表现调整。" /><div className="review-stage">{item ? <><div className="review-progress"><span>今日 {index + 1} / {reviews.length}</span><div><i style={{ width: `${((index + 1) / reviews.length) * 100}%` }} /></div></div><article className={`flash-card ${revealed ? "revealed" : ""}`}><span className="card-type">主动回忆 · 知识点 {item.knowledge_point_id}</span><h2>{item.prompt}</h2>{revealed ? <div className="card-answer"><span>核对要点</span><p>{item.answer}</p></div> : <button onClick={() => setRevealed(true)}>显示参考答案</button>}</article>{revealed && <div className="grading"><span>你的回忆质量如何？</span><div><button onClick={() => grade(1)}><b>忘记</b><small>明天再来</small></button><button onClick={() => grade(3)}><b>费力</b><small>缩短间隔</small></button><button onClick={() => grade(4)}><b>记得</b><small>正常推进</small></button><button onClick={() => grade(5)}><b>熟练</b><small>拉长间隔</small></button></div></div>}</> : <div className="review-empty"><div><Check /></div><h2>今日队列已清空</h2><p>不错，老王允许你歇会儿。新的复习项会按掌握度自动出现。</p></div>}</div></>;
}

function SettingsView({ flash }: { flash: (m: string, t?: "ok" | "error") => void }) {
  const [configured, setConfigured] = useState(false); const [verified, setVerified] = useState(false); const [key, setKey] = useState(""); const [model, setModel] = useState("deepseek-chat"); const [busy, setBusy] = useState(false);
  useEffect(() => { api<{ configured: boolean; verified: boolean; model: string }>("/api/settings/ai").then(x => { setConfigured(x.configured); setVerified(x.verified); setModel(x.model); }).catch(() => {}); }, []);
  async function save() { setBusy(true); try { await api("/api/settings/ai", { method: "PUT", body: JSON.stringify({ api_key: key, model }) }); setConfigured(true); setVerified(false); setKey(""); flash("Key 已在服务端加密保存"); } catch (e) { flash((e as Error).message, "error"); } finally { setBusy(false); } }
  async function test() { setBusy(true); try { await api("/api/settings/ai/test", { method: "POST" }); setVerified(true); flash("DeepSeek 连接验证成功"); } catch (e) { flash((e as Error).message, "error"); } finally { setBusy(false); } }
  return <><PageTitle eyebrow="SYSTEM · 本机配置" title="系统设置" copy="API Key 只在后端解密使用，不会返回浏览器，也不会写入日志。" /><div className="settings-grid"><section className="setting-card"><div className="setting-title"><div><Sparkles /><span><strong>DeepSeek</strong><small>AI 推理服务</small></span></div><em className={verified ? "verified" : configured ? "configured" : ""}>{verified ? "已验证" : configured ? "已配置" : "未配置"}</em></div><label>模型<select value={model} onChange={e => setModel(e.target.value)}><option value="deepseek-chat">deepseek-chat</option><option value="deepseek-reasoner">deepseek-reasoner</option></select></label><label>API Key<input type="password" value={key} onChange={e => setKey(e.target.value)} placeholder={configured ? "已保存，如需更换请输入新 Key" : "sk-..."} autoComplete="off" /></label><div className="setting-actions"><button className="primary" disabled={!key || busy} onClick={save}>{busy && <LoaderCircle className="spin" />}加密保存</button><button className="secondary" disabled={!configured || busy} onClick={test}>测试连接</button></div></section><section className="security-note"><ShieldCheck /><h2>密钥安全边界</h2><p>浏览器只负责提交一次密钥。服务端使用主密钥认证加密，调用 DeepSeek 时临时解密。</p><ul><li>不写入前端存储</li><li>不出现在 API 响应</li><li>不记录在服务日志</li></ul></section></div></>;
}

function ReaderDrawer({ reader, onClose }: { reader: { citation: Citation; content: string }; onClose: () => void }) {
  return <div className="drawer-scrim" onClick={onClose}><aside className="reader-drawer" onClick={e => e.stopPropagation()}><header><div><span>引用原文</span><strong>{reader.citation.document_name}</strong></div><button onClick={onClose}><X /></button></header><div className="locator"><BookOpenText />{reader.citation.locator}<em>已定位</em></div><article><div className="quote-mark">“</div><p>{reader.content}</p></article><footer><ShieldCheck />该内容来自你上传并成功解析的资料</footer></aside></div>;
}
