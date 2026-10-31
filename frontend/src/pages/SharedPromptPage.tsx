import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ArrowRight, Loader2 } from 'lucide-react';
import { apiGetSharedPrompt } from '../services/api';
import iconOnly from '../assets/clyptusap-icon.png';

/** Public view of a prompt (or answer) someone shared; offers to ask it in the app. */
export const SharedPromptPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!token) return;
    apiGetSharedPrompt(token)
      .then((shared) => {
        setPrompt(shared.content);
        setAnswer(shared.answer);
      })
      .catch(() => setNotFound(true));
  }, [token]);

  return (
    <div className="min-h-screen bg-[#fbfbf9] dark:bg-black text-slate-800 dark:text-slate-100 flex flex-col">
      <header className="px-4 sm:px-8 py-4 border-b border-slate-200 dark:border-[#14141e]">
        <Link to="/" className="inline-flex items-center gap-2 font-semibold">
          <span className="w-8 h-8 rounded-xl bg-gradient-to-tr from-orange-600 via-orange-500 to-orange-400 p-1 flex items-center justify-center">
            <img src={iconOnly} alt="" className="w-full h-full object-contain" />
          </span>
          Clyptus.AI
        </Link>
      </header>

      <main className="flex-1 w-full max-w-3xl mx-auto px-4 py-10">
        {notFound ? (
          <p className="text-center text-sm text-slate-500 dark:text-slate-400">This shared prompt doesn't exist or was removed.</p>
        ) : prompt === null ? (
          <div className="flex justify-center py-10">
            <Loader2 className="w-6 h-6 animate-spin text-orange-500" />
          </div>
        ) : (
          <>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-4">
              {answer ? 'Shared answer' : 'Shared prompt'}
            </p>
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-tr-sm px-4 py-2.5 bg-orange-50/80 dark:bg-[#13131d] border border-orange-200/70 dark:border-orange-500/20 text-sm leading-relaxed whitespace-pre-wrap break-words">
                {prompt}
              </div>
            </div>
            {answer && (
              <div className="mt-6 prose-sap text-sm text-slate-800 dark:text-slate-200 leading-relaxed break-words">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                  img: () => null,
                  a: ({ href, children }) => {
                    const safe = href && /^(https?:|mailto:)/i.test(href);
                    return safe ? <a href={href} target="_blank" rel="noopener noreferrer nofollow">{children}</a> : <>{children}</>;
                  },
                }}>{answer}</ReactMarkdown>
              </div>
            )}
            <div className="mt-8 flex justify-center">
              <button
                type="button"
                onClick={() => navigate('/app', { state: { prefillPrompt: prompt } })}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-sm font-semibold shadow-md shadow-orange-500/20 transition cursor-pointer"
              >
                Ask Clyptus.AI this question
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  );
};
