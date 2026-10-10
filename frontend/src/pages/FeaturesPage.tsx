import React from 'react';
import { ArrowRight, BookOpen, Boxes, MessageCircle, Search, ShieldCheck, Sparkles, Workflow } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Footer } from '../components/footer/Footer';
import { PublicNav } from '../components/navbar/PublicNav';
import { PageMeta } from '../components/ui/PageMeta';

const items = [
  [Sparkles, 'SAP answers with context', 'Ask in everyday technical language and get responses shaped strictly by indexed enterprise SAP knowledge.'],
  [Search, 'Hybrid dense + lexical retrieval', 'Combines sentence-transformers vector embeddings with BM25 keyword matching for optimal recall.'],
  [Boxes, 'Deep BRIM domain specialization', 'Exhaustive coverage of Convergent Mediation, Convergent Charging, Convergent Invoicing, FI-CA, and SOM.'],
  [MessageCircle, 'Conversations that retain thread context', 'Multi-turn query rewriting preserves conversational intent across follow-up technical questions.'],
  [BookOpen, 'Verified page-level citations', 'Every answer links to specific document chunks, pages, and confidence scores.'],
  [ShieldCheck, 'Grounding & guardrails', 'Real-time hallucination prevention guardrails reject unsupported assertions and non-SAP queries.'],
] as const;

export const FeaturesPage: React.FC = () => {
  return (
    <>
      <PageMeta
        title="Features"
        description="Explore SAP-focused answers, retrieval and BRIM knowledge with Clyptusap.ai."
      />
      <PublicNav />
      <main className="inner-page">
        <section className="inner-hero section-wrap">
          <span className="eyebrow">SAP + BRIM AI KNOWLEDGE ASSISTANT</span>
          <h1>
            Good questions<br />
            <span>deserve verified SAP context.</span>
          </h1>
          <p>
            Clyptusap.ai retrieves relevant information from indexed SAP knowledge before generating an answer, backed by streaming citations and cross-encoder reranking.
          </p>
          <Link className="text-link" to="/how-it-works">
            See how it works <ArrowRight size={16} />
          </Link>
          <div className="inner-hero-art">
            <div className="art-stack">
              <span><Workflow size={17} /> SAP Technical Question</span>
              <span><Search size={17} /> Hybrid Retrieved Context</span>
              <span><Sparkles size={17} /> Grounded Streaming Answer</span>
            </div>
          </div>
        </section>

        <section className="section section-wrap inner-feature-list">
          <span className="eyebrow">BUILT FOR SAP · DEEPLY FOCUSED ON BRIM</span>
          <div className="inner-feature-grid">
            {items.map(([Icon, title, text], index) => (
              <article className="inner-feature" key={title}>
                <span className="section-index">0{index + 1}</span>
                <span className="feature-icon"><Icon size={19} /></span>
                <h2>{title}</h2>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="inner-bottom-cta">
          <span className="eyebrow">SAP KNOWLEDGE, IN CONTEXT</span>
          <h2>Have an SAP question?</h2>
          <Link className="button button-dark" to="/login">
            Ask Clyptusap.ai <ArrowRight size={16} />
          </Link>
        </section>
      </main>
      <Footer />
    </>
  );
};
