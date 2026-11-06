import React from 'react';
import { ArrowRight, BookOpen, Boxes, MessageCircle, Search, ShieldCheck, Sparkles, Workflow } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Footer } from '../components/footer/Footer';
import { PublicNav } from '../components/navbar/PublicNav';
import { PageMeta } from '../components/ui/PageMeta';

const items = [
  [Sparkles, 'Low by default, High on demand', 'Every chat starts in Low with fast, direct answers. Press the High button to have the answer researched from the SAP knowledge base and verified before it is shown; press it again to go back to Low.'],
  [Search, 'Hybrid retrieval', 'Dense vector embeddings, BM25 keyword ranking and exact SAP identifier matching, merged with reciprocal rank fusion.'],
  [Boxes, 'SAP BRIM focus', 'Subscription Order Management, Convergent Charging, Convergent Invoicing, FI-CA and Convergent Mediation.'],
  [MessageCircle, 'Conversation memory', 'Follow-ups are resolved against the last 20 messages, a running summary of older turns, and recall of earlier questions.'],
  [BookOpen, 'Curated, access-controlled sources', 'Administrators manage the knowledge base, with source-authority tiers and document access groups. Admins can inspect the evidence behind any answer.'],
  [ShieldCheck, 'Grounding and guardrails', 'Claim-level verification rejects unsupported statements and invented SAP identifiers; non-SAP questions are declined.'],
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
            Clyptusap.ai retrieves relevant SAP knowledge before generating an answer, then checks the answer claim by claim against that evidence.
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
