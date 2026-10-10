import React from 'react';
import { ArrowDown, ArrowUpRight, Boxes, MessageCircle, Search, ShieldCheck, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Footer } from '../components/footer/Footer';
import { PublicNav } from '../components/navbar/PublicNav';
import { PageMeta } from '../components/ui/PageMeta';

const steps = [
  [MessageCircle, 'Ask', 'Ask your SAP or BRIM question naturally, whether regarding a transaction code, configuration path, process flow, or customizing table.', 'No special syntax required.'],
  [Search, 'Retrieve', 'Dense vector similarity (MiniLM-L6) and BM25 lexical search run in parallel over pre-indexed document chunks.', 'Hybrid dense & lexical retrieval.'],
  [Boxes, 'Context & Rerank', 'A cross-encoder model scores candidate chunks, elevating the most contextually relevant technical excerpts.', 'Precision reranking.'],
  [Sparkles, 'Generate & Stream', 'The LLM streams tokens via SSE with ChatGPT-style thinking and bouncing animation indicators.', 'Real-time interactive streaming.'],
  [ShieldCheck, 'Ground & Cite', 'The response is checked for hallucination, assigned a grounding score, and annotated with exact document sources.', 'Enterprise verification.'],
] as const;

export const HowItWorksPage: React.FC = () => {
  return (
    <>
      <PageMeta
        title="How It Works"
        description="Learn how Clyptusap.ai retrieves SAP knowledge to generate grounded answers."
      />
      <PublicNav />
      <main className="inner-page">
        <section className="inner-hero how-hero section-wrap">
          <span className="eyebrow">RETRIEVAL-AUGMENTED GENERATION</span>
          <h1>
            From question<br />
            to <span>grounded answer.</span>
          </h1>
          <p>
            Clyptusap.ai searches its indexed SAP knowledge base for relevant technical documentation, uses that context to generate answers, and presents verifiable sources.
          </p>
          <a className="scroll-hint inner-scroll" href="#process">
            FOLLOW THE ARCHITECTURE <ArrowDown size={14} />
          </a>
          <div className="how-hero-flow">
            <span><MessageCircle size={17} /> Question</span>
            <ArrowUpRight size={16} />
            <span><Search size={17} /> Hybrid Retrieval</span>
            <ArrowUpRight size={16} />
            <span><Sparkles size={17} /> Answer + Citations</span>
          </div>
        </section>

        <section className="section section-wrap how-process" id="process">
          <span className="eyebrow">FROM QUESTION TO RESPONSE</span>
          <div className="how-steps">
            {steps.map(([Icon, title, text, note], i) => (
              <article className="how-step" key={title}>
                <span className="how-step-number">0{i + 1}</span>
                <div className="how-step-icon"><Icon size={20} /></div>
                <div>
                  <h2>{title}</h2>
                  <p>{text}</p>
                  <span className="how-step-note">{note}</span>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="inner-bottom-cta">
          <span className="eyebrow">READY TO TEST?</span>
          <h2>Experience the SAP Knowledge Assistant</h2>
          <Link className="button button-dark" to="/login">
            Ask Clyptusap.ai <ArrowUpRight size={16} />
          </Link>
        </section>
      </main>
      <Footer />
    </>
  );
};
