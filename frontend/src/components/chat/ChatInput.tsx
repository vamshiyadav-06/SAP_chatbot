import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Mic, MicOff, Square } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  onStop?: () => void;
  isLoading: boolean;
}

// Extend the Window interface for SpeechRecognition browser API
declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    SpeechRecognition: any;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    webkitSpeechRecognition: any;
  }
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSendMessage, onStop, isLoading }) => {
  const [input, setInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const recognitionRef = useRef<any>(null);
  const interimRef = useRef('');

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
  }, [input]);

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

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || isLoading) return;
    if (isListening) stopListening();

    onSendMessage(input.trim());
    setInput('');
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

  return (
    <div className="w-full max-w-4xl mx-auto px-4 pb-4 pt-2">
      {/* Voice error toast */}
      {voiceError && (
        <div className="mb-2 px-3 py-2 rounded-xl bg-rose-950/60 border border-rose-700/50 text-xs text-rose-300 flex items-center justify-between gap-2">
          <span>{voiceError}</span>
          <button onClick={() => setVoiceError(null)} className="text-rose-400 hover:text-rose-200 transition font-bold shrink-0">✕</button>
        </div>
      )}

      <form
        onSubmit={handleSubmit}
        className={`relative bg-white dark:bg-[#09090e] border rounded-2xl shadow-sm dark:shadow-2xl transition-all duration-200 ${
          isListening
            ? 'border-rose-500/70 ring-2 ring-rose-500/25'
            : 'border-slate-300 dark:border-[#1f1f2c] focus-within:border-orange-500 focus-within:ring-2 focus-within:ring-orange-500/20 focus-within:shadow-md'
        }`}
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isListening ? 'Listening... speak now' : 'Ask anything about SAP...'}
          rows={1}
          disabled={isLoading}
          className="w-full bg-transparent text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 text-sm px-4 pt-3.5 pb-12 focus:outline-none resize-none max-h-48 min-h-[52px]"
        />

        <div className="absolute bottom-2.5 left-3 right-3 flex items-center justify-between">
          {/* Left side: mic status indicator */}
          <div className="flex items-center gap-2">
            {isListening && (
              <span className="flex items-center gap-1.5 text-[11px] text-rose-400 font-medium animate-pulse">
                <span className="w-2 h-2 rounded-full bg-rose-500 inline-block animate-pulse" />
                Listening...
              </span>
            )}
          </div>

          {/* Right side: voice + send buttons */}
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
                {isListening ? (
                  <MicOff className="w-4 h-4" />
                ) : (
                  <Mic className="w-4 h-4" />
                )}
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
                disabled={!input.trim()}
                title="Send message"
                className="flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-r from-orange-600 to-orange-500 hover:from-orange-500 hover:to-orange-400 disabled:opacity-40 disabled:hover:from-orange-600 disabled:hover:to-orange-500 text-white shadow-md shadow-orange-500/30 transition duration-150 disabled:cursor-not-allowed cursor-pointer"
              >
                <Send className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </form>

      <div className="text-center mt-2">
        <span className="text-[11px] text-slate-400 dark:text-slate-500">
          SAP Knowledge Assistant grounded in verified enterprise documentation. Non-SAP queries are rejected.
        </span>
      </div>

    </div>
  );
};
