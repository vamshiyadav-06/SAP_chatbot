import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send,
  Mic,
  MicOff,
  Square,
  Plus,
  X,
  FileText,
  FileSpreadsheet,
  FileCode,
  Image as ImageIcon,
  FolderOpen,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { apiExtractDocument } from '../../services/api';
import type { DocumentAttachment } from '../../types';

interface ChatInputProps {
  onSendMessage: (message: string, attachments?: DocumentAttachment[]) => void;
  onStop?: () => void;
  isLoading: boolean;
  /** Text to start with, e.g. a prompt opened from a share link. */
  initialInput?: string;
}

interface LocalAttachment {
  id: string;
  file: File;
  name: string;
  size: number;
  file_type: string;
  status: 'extracting' | 'ready' | 'error';
  page_count?: number;
  char_count?: number;
  text?: string;
  preview?: string;
  errorMessage?: string;
  thumbUrl?: string;
  detected_question?: string | null;
  analysis_method?: string | null;
}

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'bmp'];
const PASTE_IMAGE_TYPES: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
  'image/bmp': 'bmp',
};
const IMAGE_ACCEPT = '.png,.jpg,.jpeg,.webp,.bmp,image/png,image/jpeg,image/webp,image/bmp';

const isImageType = (fileType: string) => IMAGE_EXTENSIONS.includes(fileType);

// Extend Window interface for SpeechRecognition browser API
declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    SpeechRecognition: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    webkitSpeechRecognition: any;
  }
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, onStop, isLoading, initialInput = '' }) => {
  const [input, setInput] = useState(initialInput);
  const [attachments, setAttachments] = useState<LocalAttachment[]>([]);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<any>(null);
  const interimRef = useRef('');
  const menuRef = useRef<HTMLDivElement>(null);
  const attachButtonRef = useRef<HTMLButtonElement>(null);

  const pdfInputRef = useRef<HTMLInputElement>(null);
  const docxInputRef = useRef<HTMLInputElement>(null);
  const dataInputRef = useRef<HTMLInputElement>(null);
  const allInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  // Close attachment dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(event.target as Node) &&
        attachButtonRef.current &&
        !attachButtonRef.current.contains(event.target as Node)
      ) {
        setShowAttachMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Detect browser support for SpeechRecognition
  useEffect(() => {
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    setVoiceSupported(!!SpeechRecognitionAPI);
  }, []);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [input, attachments]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    interimRef.current = '';
    setIsListening(false);
  }, []);

  const startListening = useCallback(() => {
    setVoiceError(null);
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionAPI) return;

    const recognition = new SpeechRecognitionAPI();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = true;
    recognition.maxAlternatives = 1;

    recognitionRef.current = recognition;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      if (finalTranscript) {
        setInput((prev) => {
          const base = prev.endsWith(' ') || prev === '' ? prev : prev + ' ';
          return (base + finalTranscript).trimStart();
        });
      }
      interimRef.current = interimTranscript;
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === 'not-allowed') {
        setVoiceError('Microphone access denied. Please allow microphone permissions.');
      } else if (event.error !== 'aborted') {
        setVoiceError('Voice recognition error. Please try again.');
      }
      stopListening();
    };

    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
      interimRef.current = '';
    };

    recognition.start();
  }, [stopListening]);

  const toggleVoice = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getFileBadgeColor = (ext: string) => {
    switch (ext) {
      case 'pdf':
        return 'bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30';
      case 'docx':
      case 'doc':
        return 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30';
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'webp':
      case 'bmp':
        return 'bg-violet-500/15 text-violet-600 dark:text-violet-400 border-violet-500/30';
      case 'csv':
      case 'xlsx':
      case 'xls':
        return 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30';
      case 'json':
      case 'xml':
      case 'sql':
        return 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30';
      default:
        return 'bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30';
    }
  };

  const handleFilesSelected = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;
    setShowAttachMenu(false);

    const newItems: LocalAttachment[] = fileArray.map((f) => {
      const fileType = f.name.split('.').pop()?.toLowerCase() || 'txt';
      return {
        id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
        file: f,
        name: f.name,
        size: f.size,
        file_type: fileType,
        status: 'extracting',
        thumbUrl: isImageType(fileType) ? URL.createObjectURL(f) : undefined,
      };
    });

    setAttachments((prev) => [...prev, ...newItems]);

    for (const item of newItems) {
      try {
        const res = await apiExtractDocument(item.file);
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === item.id
              ? {
                  ...a,
                  status: 'ready',
                  page_count: res.page_count,
                  char_count: res.char_count,
                  text: res.text,
                  preview: res.preview,
                  detected_question: res.detected_question,
                  analysis_method: res.analysis_method,
                }
              : a
          )
        );
      } catch (err: any) {
        setAttachments((prev) =>
          prev.map((a) =>
            a.id === item.id
              ? {
                  ...a,
                  status: 'error',
                  errorMessage: err.message || 'Could not extract text',
                }
              : a
          )
        );
      }
    }
  };

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = event.currentTarget.files;
    if (selected) void handleFilesSelected(selected);
    // Allow selecting the same file again after removing it or correcting an extraction issue.
    event.currentTarget.value = '';
  };

  // Ctrl+V / Cmd+V of a screenshot attaches it like an uploaded image; plain text pastes normally.
  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const images = Array.from(e.clipboardData.items)
      .filter((item) => item.kind === 'file' && item.type in PASTE_IMAGE_TYPES)
      .map((item) => item.getAsFile())
      .filter((f): f is File => f !== null);
    if (images.length === 0) return;
    e.preventDefault();
    const stamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
    const named = images.map(
      (f, i) =>
        new File([f], `pasted-image-${stamp}${images.length > 1 ? `-${i + 1}` : ''}.${PASTE_IMAGE_TYPES[f.type]}`, {
          type: f.type,
        })
    );
    void handleFilesSelected(named);
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => {
      const removed = prev.find((a) => a.id === id);
      if (removed?.thumbUrl) URL.revokeObjectURL(removed.thumbUrl);
      return prev.filter((a) => a.id !== id);
    });
  };

  const isExtracting = attachments.some((a) => a.status === 'extracting');

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isLoading || isExtracting) return;

    const readyAttachments: DocumentAttachment[] = attachments
      .filter((a) => a.status === 'ready' && a.text)
      .map((a) => ({
        name: a.name,
        file_type: a.file_type,
        size_bytes: a.size,
        page_count: a.page_count,
        text: a.text!,
        preview: a.preview,
      }));

    const trimmedInput = input.trim();
    if (!trimmedInput && readyAttachments.length === 0) return;

    if (isListening) stopListening();

    const readyImages = attachments.filter((a) => a.status === 'ready' && a.text && isImageType(a.file_type));
    const detectedQuestions = readyImages
      .map((a) => a.detected_question?.trim())
      .filter((q): q is string => !!q);

    let defaultQuery = 'Please analyze the attached document(s), summarizing key sections and explaining core findings.';
    if (readyImages.length > 0 && readyImages.length === readyAttachments.length) {
      defaultQuery = detectedQuestions.length > 0
        ? `Explain what the attached image shows and give clear step-by-step instructions to resolve this: ${detectedQuestions.join(' Also: ')}`
        : 'Explain what the attached image shows. If it contains an error, issue or question, explain the likely cause and give clear step-by-step instructions to fix or answer it.';
    }
    const finalQuery = trimmedInput || defaultQuery;

    onSendMessage(finalQuery, readyAttachments);
    setInput('');
    attachments.forEach((a) => a.thumbUrl && URL.revokeObjectURL(a.thumbUrl));
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files);
    }
  };

  return (
    <div className="w-full max-w-4xl mx-auto px-4 pb-4 pt-2">
      {/* Hidden File Inputs */}
      <input
        type="file"
        ref={pdfInputRef}
        accept=".pdf"
        multiple
        className="hidden"
        onChange={handleFileInputChange}
      />
      <input
        type="file"
        ref={docxInputRef}
        accept=".docx"
        multiple
        className="hidden"
        onChange={handleFileInputChange}
      />
      <input
        type="file"
        ref={dataInputRef}
        accept=".txt,.md,.csv,.json,.log,.tsv,.xml,.sql,.yaml,.yml"
        multiple
        className="hidden"
        onChange={handleFileInputChange}
      />
      <input
        type="file"
        ref={imageInputRef}
        accept={IMAGE_ACCEPT}
        multiple
        className="hidden"
        onChange={handleFileInputChange}
      />
      <input
        type="file"
        ref={allInputRef}
        accept={`.pdf,.docx,${IMAGE_ACCEPT},.txt,.md,.csv,.json,.log,.tsv,.xml,.sql,.yaml,.yml`}
        multiple
        className="hidden"
        onChange={handleFileInputChange}
      />

      {/* Voice error toast */}
      {voiceError && (
        <div className="mb-2 px-3 py-2 rounded-xl bg-rose-950/60 border border-rose-700/50 text-xs text-rose-300 flex items-center justify-between gap-2">
          <span>{voiceError}</span>
          <button onClick={() => setVoiceError(null)} className="text-rose-400 hover:text-rose-200 transition font-bold shrink-0">✕</button>
        </div>
      )}

      {/* Main Input Form with Drag & Drop */}
      <form
        onSubmit={handleSubmit}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`relative bg-white dark:bg-[#09090e] border rounded-2xl shadow-sm dark:shadow-2xl transition-all duration-200 flex flex-col ${
          isDragging
            ? 'border-orange-500 ring-2 ring-orange-500/30 bg-orange-50/20 dark:bg-orange-950/10'
            : isListening
            ? 'border-rose-500/70 ring-2 ring-rose-500/25'
            : 'border-slate-300 dark:border-[#1f1f2c] focus-within:border-orange-500 focus-within:ring-2 focus-within:ring-orange-500/20 focus-within:shadow-md'
        }`}
      >
        {/* Drag Overlay indicator */}
        {isDragging && (
          <div className="absolute inset-0 z-30 bg-orange-500/10 dark:bg-orange-500/15 backdrop-blur-[2px] rounded-2xl flex items-center justify-center border-2 border-dashed border-orange-500 pointer-events-none">
            <div className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white dark:bg-[#0c0c14] border border-orange-500/40 text-orange-600 dark:text-orange-400 text-xs font-semibold shadow-lg">
              <Plus className="w-4 h-4" />
              <span>Drop documents here to attach</span>
            </div>
          </div>
        )}

        {/* Attachment Preview Chips inside the input container */}
        {attachments.length > 0 && (
          <div className="px-3 pt-3 pb-1 flex flex-wrap gap-2 items-center border-b border-slate-100 dark:border-[#161622]">
            {attachments.map((att) => {
              const isPdf = att.file_type === 'pdf';
              const isDoc = att.file_type === 'docx' || att.file_type === 'doc';
              const isData = ['csv', 'json', 'xlsx'].includes(att.file_type);
              const isImage = isImageType(att.file_type);

              return (
                <div
                  key={att.id}
                  className="group relative flex items-center gap-2.5 px-3 py-1.5 rounded-xl bg-slate-100 dark:bg-[#12121a] border border-slate-200 dark:border-[#222230] text-xs transition-all hover:border-orange-400 dark:hover:border-orange-500/40 shadow-xs max-w-xs"
                >
                  {/* File Format Icon (thumbnail for images) */}
                  {isImage && att.thumbUrl ? (
                    <img
                      src={att.thumbUrl}
                      alt=""
                      className="w-8 h-8 rounded-md object-cover border border-violet-500/30 shrink-0"
                    />
                  ) : (
                  <div className={`p-1 rounded-md border shrink-0 ${getFileBadgeColor(att.file_type)}`}>
                    {isPdf ? (
                      <FileText className="w-3.5 h-3.5" />
                    ) : isDoc ? (
                      <FileText className="w-3.5 h-3.5" />
                    ) : isData ? (
                      <FileSpreadsheet className="w-3.5 h-3.5" />
                    ) : isImage ? (
                      <ImageIcon className="w-3.5 h-3.5" />
                    ) : (
                      <FileCode className="w-3.5 h-3.5" />
                    )}
                  </div>
                  )}

                  {/* Name and extraction status */}
                  <div className="flex flex-col min-w-0 pr-1">
                    <span className="font-semibold text-slate-800 dark:text-slate-100 truncate max-w-[170px]" title={att.name}>
                      {att.name}
                    </span>
                    <span className="text-[10px] text-slate-500 dark:text-slate-400 flex items-center gap-1">
                      {att.status === 'extracting' && (
                        <>
                          <Loader2 className="w-2.5 h-2.5 text-orange-500 animate-spin" />
                          <span>{isImage ? 'Reading image...' : 'Extracting content...'}</span>
                        </>
                      )}
                      {att.status === 'ready' && (
                        <>
                          <CheckCircle2 className="w-2.5 h-2.5 text-emerald-500" />
                          <span>
                            {isImage
                              ? `${att.analysis_method === 'ocr' ? 'Text read (OCR)' : 'Image analysed'} · `
                              : att.page_count ? `${att.page_count} ${att.page_count === 1 ? 'page' : 'pages'} · ` : ''}
                            {formatFileSize(att.size)}
                          </span>
                        </>
                      )}
                      {att.status === 'error' && (
                        <>
                          <AlertCircle className="w-2.5 h-2.5 text-rose-500" />
                          <span className="text-rose-500 truncate max-w-[130px]">{att.errorMessage || 'Failed'}</span>
                        </>
                      )}
                    </span>
                  </div>

                  {/* Remove attachment button */}
                  <button
                    type="button"
                    onClick={() => removeAttachment(att.id)}
                    className="p-1 rounded-full text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-800 transition cursor-pointer"
                    title="Remove file"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Text Input */}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={
            isListening
              ? 'Listening... speak now'
              : attachments.length > 0
              ? 'Ask a question about the attachment, or press Enter to have it explained...'
              : 'Ask anything about SAP, paste a screenshot (Ctrl+V), or attach documents with +'
          }
          rows={1}
          disabled={isLoading}
          className="w-full bg-transparent text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 text-sm px-4 pt-3.5 pb-12 focus:outline-none resize-none max-h-48 min-h-[52px]"
        />

        {/* Bottom Actions Bar */}
        <div className="absolute bottom-2.5 left-3 right-3 flex items-center justify-between pointer-events-auto">
          {/* Left side: ChatGPT-Style '+' Button & Mic Status */}
          <div className="relative flex items-center gap-2">
            {/* '+' Add Button */}
            <div className="relative">
              <button
                ref={attachButtonRef}
                type="button"
                onClick={() => setShowAttachMenu((prev) => !prev)}
                disabled={isLoading}
                title="Add attachments (PDF, Word, PNG, Text, Data)"
                className={`flex items-center justify-center w-8 h-8 rounded-xl transition duration-150 disabled:opacity-40 disabled:cursor-not-allowed ${
                  showAttachMenu
                    ? 'bg-orange-500 text-white shadow-md shadow-orange-500/25 ring-2 ring-orange-500/30'
                    : 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Plus className={`w-4 h-4 transition-transform duration-200 ${showAttachMenu ? 'rotate-45' : ''}`} />
              </button>

              {/* ChatGPT-style Attachment Popup Menu */}
              {showAttachMenu && (
                <div
                  ref={menuRef}
                  className="absolute bottom-11 left-0 z-40 w-72 bg-white dark:bg-[#0c0c14] border border-slate-200 dark:border-[#222234] rounded-2xl shadow-2xl p-2 animate-in fade-in zoom-in-95 duration-150 backdrop-blur-md"
                >
                  <div className="px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-[#1a1a26] mb-1">
                    Attach Documents & Content
                  </div>

                  {/* Option 1: PDF Document */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowAttachMenu(false);
                      pdfInputRef.current?.click();
                    }}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left hover:bg-orange-50/80 dark:hover:bg-[#161622] text-slate-800 dark:text-slate-200 hover:text-orange-600 dark:hover:text-orange-400 transition cursor-pointer group"
                  >
                    <div className="w-8 h-8 rounded-lg bg-red-500/10 dark:bg-red-500/20 text-red-600 dark:text-red-400 flex items-center justify-center border border-red-500/25 group-hover:scale-105 transition-transform">
                      <FileText className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold">Upload PDF Document</span>
                      <span className="text-[11px] text-slate-500 dark:text-slate-400">Extracts pages, text & tables (.pdf)</span>
                    </div>
                  </button>

                  {/* Option 2: Word Document */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowAttachMenu(false);
                      docxInputRef.current?.click();
                    }}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left hover:bg-blue-50/80 dark:hover:bg-[#161622] text-slate-800 dark:text-slate-200 hover:text-blue-600 dark:hover:text-blue-400 transition cursor-pointer group"
                  >
                    <div className="w-8 h-8 rounded-lg bg-blue-500/10 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 flex items-center justify-center border border-blue-500/25 group-hover:scale-105 transition-transform">
                      <FileText className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold">Upload Word Document</span>
                      <span className="text-[11px] text-slate-500 dark:text-slate-400">Functional specs & guides (.docx)</span>
                    </div>
                  </button>

                  {/* Option 3: Text & Data */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowAttachMenu(false);
                      dataInputRef.current?.click();
                    }}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left hover:bg-emerald-50/80 dark:hover:bg-[#161622] text-slate-800 dark:text-slate-200 hover:text-emerald-600 dark:hover:text-emerald-400 transition cursor-pointer group"
                  >
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center border border-emerald-500/25 group-hover:scale-105 transition-transform">
                      <FileSpreadsheet className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold">Upload Text & Data</span>
                      <span className="text-[11px] text-slate-500 dark:text-slate-400">Notes, CSV, JSON, logs & markdown</span>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setShowAttachMenu(false);
                      imageInputRef.current?.click();
                    }}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left hover:bg-violet-50/80 dark:hover:bg-[#161622] text-slate-800 dark:text-slate-200 hover:text-violet-600 dark:hover:text-violet-400 transition cursor-pointer group"
                  >
                    <div className="w-8 h-8 rounded-lg bg-violet-500/10 dark:bg-violet-500/20 text-violet-600 dark:text-violet-400 flex items-center justify-center border border-violet-500/25 group-hover:scale-105 transition-transform">
                      <ImageIcon className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold">Upload Image or Screenshot</span>
                      <span className="text-[11px] text-slate-500 dark:text-slate-400">Reads and explains errors & questions (.png, .jpg, .webp)</span>
                    </div>
                  </button>

                  {/* Option 4: Browse All Files */}
                  <button
                    type="button"
                    onClick={() => {
                      setShowAttachMenu(false);
                      allInputRef.current?.click();
                    }}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left hover:bg-slate-100 dark:hover:bg-[#161622] text-slate-800 dark:text-slate-200 transition cursor-pointer group border-t border-slate-100 dark:border-[#1a1a26] mt-1 pt-2"
                  >
                    <div className="w-8 h-8 rounded-lg bg-slate-500/10 dark:bg-slate-500/20 text-slate-600 dark:text-slate-400 flex items-center justify-center border border-slate-500/25 group-hover:scale-105 transition-transform">
                      <FolderOpen className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold">Upload from Computer</span>
                      <span className="text-[11px] text-slate-500 dark:text-slate-400">Browse any supported document</span>
                    </div>
                  </button>
                </div>
              )}
            </div>

            {/* Listening status */}
            {isListening && (
              <span className="flex items-center gap-1.5 text-[11px] text-rose-500 font-medium animate-pulse">
                <span className="w-2 h-2 rounded-full bg-rose-500 inline-block animate-pulse" />
                Listening...
              </span>
            )}
          </div>

          {/* Right side: Voice + Send Buttons */}
          <div className="flex items-center gap-1.5">
            {/* Mic Button */}
            {voiceSupported && (
              <button
                type="button"
                onClick={toggleVoice}
                disabled={isLoading}
                title={isListening ? 'Stop recording' : 'Voice input'}
                className={`flex items-center justify-center w-8 h-8 rounded-xl transition duration-150 disabled:opacity-40 disabled:cursor-not-allowed ${
                  isListening
                    ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-600/30 animate-pulse'
                    : 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
              </button>
            )}

            {/* Send / Stop Button */}
            {isLoading ? (
              <button
                type="button"
                onClick={onStop}
                title="Stop generating"
                className="flex items-center justify-center w-8 h-8 rounded-xl bg-rose-600 hover:bg-rose-500 text-white shadow-md shadow-rose-600/30 transition duration-150 cursor-pointer"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={(!input.trim() && !attachments.some((a) => a.status === 'ready' && !!a.text)) || isExtracting}
                title={isExtracting ? 'Extracting document text...' : 'Send message'}
                className="flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-r from-orange-600 to-orange-500 hover:from-orange-500 hover:to-orange-400 disabled:opacity-40 disabled:hover:from-orange-600 disabled:hover:to-orange-500 text-white shadow-md shadow-orange-500/30 transition duration-150 disabled:cursor-not-allowed cursor-pointer"
              >
                {isExtracting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </button>
            )}
          </div>
        </div>
      </form>

      <div className="text-center mt-2 flex items-center justify-center gap-1.5 flex-wrap">
        <span className="text-[11px] text-slate-400 dark:text-slate-500">
          Click <strong className="text-orange-500 font-semibold">+</strong> to upload documents or images, or paste a screenshot with <strong className="font-semibold">Ctrl+V</strong>. Clyptus.AI reads it and explains any error or question it shows.
        </span>
      </div>
    </div>
  );
};
