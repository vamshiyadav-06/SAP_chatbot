import React from 'react';
import { motion } from 'framer-motion';
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Boxes,
  Compass,
  FileText,
  Gauge,
  MessageCircle,
  Search,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { FaqSection } from '../components/landing/FaqSection';
import { VideoShowcase } from '../components/landing/VideoShowcase';
import { Footer } from '../components/footer/Footer';
import { PublicNav } from '../components/navbar/PublicNav';
import { PageMeta } from '../components/ui/PageMeta';

const brimAreas = [
  { abbreviation: 'CM', title: 'Convergent Mediation', icon: Workflow },
  { abbreviation: 'CC', title: 'Convergent Charging', icon: Gauge },
  { abbreviation: 'CI', title: 'Convergent Invoicing', icon: FileText },
  { abbreviation: 'FI-CA', title: 'Contract Accounts Receivable & Payable', icon: BookOpen },
  { abbreviation: 'SOM', title: 'Subscription Order Management', icon: Boxes },
  { abbreviation: 'SAP + BRIM', title: 'Connected knowledge across the entire SAP landscape.', icon: Compass },
];

const retrievalSteps = [
  ['01', 'Question', 'Start with your SAP question in everyday technical or functional terms.', MessageCircle],
  ['02', 'Retrieve', 'Dense embeddings & BM25 search across indexed enterprise manuals.', Search],
  ['03', 'Rank', 'Cross-encoder reranking prioritizes highest-relevance context.', Gauge],
  ['04', 'Generate', 'Real-time streaming generation informed strictly by verified knowledge.', Sparkles],
  ['05', 'Ground', 'Automated grounding checks verify factual alignment and prevent hallucination.', ShieldCheck],
  ['06', 'Respond', 'Interactive answers with verified citations and grounding confidence.', ArrowRight],
] as const;

const useCases = [
  ['Configuration', 'Where is this specific SAP setting configured in SPRO?'],
  ['Transaction codes', 'Which transaction code manages billable items or billing runs?'],
  ['Concepts', 'What is the lifecycle of a billable item in Convergent Invoicing?'],
  ['Processes', 'Walk me step-by-step through the SAP BRIM rating and charging flow.'],
  ['Troubleshooting', 'Billing completed but no invoice document created. What should I check?'],
  ['Documentation', 'Synthesize complex FI-CA clearing rules from official SAP documentation.'],
];

const exampleQuestions = [
  'What is FKKBIXCIT_CONF?',
  'Where are document types configured in FI-CA?',
  'How does Convergent Charging handle charge plans?',
  'Explain the complete BRIM billing flow.',
  'Why was my billing document not generated?',
  'What is the purpose of transaction FKKBIX_BIT_MON?',
];

function ResponsePreview({ specific = false }: { specific?: boolean }) {
  return (
    <article className="response-preview">
      <div className="response-preview-top">
        <span><span className="live-dot" /> LIVE PLATFORM ARCHITECTURE</span>
        <span>Developer-Managed RAG</span>
      </div>
      <div className="response-preview-question">
        <span>QUESTION</span>
        <p>{specific ? 'Where is this SAP configuration maintained in SPRO?' : 'What is transaction FKKBIXCIT_CONF?'}</p>
      </div>
      <div className="response-preview-answer">
        <span>ANSWER</span>
        <p>Relevant SAP details are retrieved from indexed enterprise manuals with verified citations and cross-encoder validation.</p>
      </div>
      {specific && (
        <div className="response-preview-row">
          <strong>Configuration path</strong>
          <span>IMG &gt; Financial Accounting &gt; Contract Accounts Receivable & Payable &gt; Convergent Invoicing</span>
        </div>
      )}
      <div className="response-preview-meta">
        <div><strong>Grounding Score</strong><span>0.94 · Highly Grounded</span></div>
        <div><strong>Source Type</strong><span>Knowledge Base</span></div>
        <div><strong>Citations</strong><span>3 Verified Doc Chunks</span></div>
      </div>
    </article>
  );
}

export const LandingPage: React.FC = () => {
  return (
    <>
      <PageMeta
        title="SAP + BRIM AI Knowledge Assistant"
        description="Clyptusap.ai is an enterprise AI knowledge assistant dedicated to SAP and SAP BRIM."
      />
      <PublicNav />
      <main>
        {/* Hero Section */}
        <section className="hero section-wrap">
          <motion.div
            className="hero-copy"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55 }}
          >
            <div className="hero-kicker">
              <span className="kicker-mark">C</span> SAP + BRIM ENTERPRISE ASSISTANT
            </div>
            <h1>
              Your SAP questions.<br />
              <span>Answered with</span><br />
              exact context.
            </h1>
            <p className="hero-description">
              Clyptusap.ai is an AI-powered SAP knowledge platform built to help consultants and developers navigate SAP & BRIM with grounded, cited responses.
            </p>
            <div className="hero-actions">
              <Link className="button button-brand" to="/login">
                Ask Clyptusap.ai <ArrowUpRight size={17} />
              </Link>
              <Link className="text-link" to="/how-it-works">
                See how it works <ArrowRight size={16} />
              </Link>
            </div>
            <div className="hero-trust">
              <span className="trust-line" />
              SAP-focused · Hybrid Retrieval · Grounded in verified documentation
            </div>
          </motion.div>

          <motion.div
            className="hero-visual"
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.14 }}
          >
            <VideoShowcase />
            <div className="video-supporting-copy">
              <strong>See Clyptusap.ai in action</strong>
              <p>
                Ask a question. Clyptusap.ai retrieves relevant SAP knowledge, generates answers with real-time ChatGPT streaming animations, and surfaces verified citations.
              </p>
            </div>
          </motion.div>
          <a className="scroll-hint" href="#why">
            <span>SCROLL TO EXPLORE</span>
            <ArrowDown size={14} />
          </a>
        </section>

        {/* Statement Band */}
        <section className="statement-band" id="why">
          <div className="statement-inner">
            <span className="eyebrow">ENTERPRISE SAP KNOWLEDGE, IN CONTEXT</span>
            <p>
              From complex SAP configuration doubts<br />
              <span>to verified answers and authoritative documentation.</span>
            </p>
          </div>
        </section>

        {/* Intro Section */}
        <section className="section section-wrap intro-section">
          <div className="intro-label">
            <span className="section-index">01</span>
            <span className="eyebrow">WHAT IS CLYTUSAP.AI</span>
          </div>
          <div className="intro-content">
            <h2>An AI assistant<br />built specifically for <span>SAP knowledge.</span></h2>
            <p>
              SAP is vast and intricate. Answers depend on precise module interactions, transaction codes, custom customizing settings, and system architectures.
            </p>
            <p>
              Clyptusap.ai uses Developer-Managed RAG to retrieve the exact documentation before answering, eliminating hallucinations and delivering enterprise grounding.
            </p>
            <Link className="text-link" to="/how-it-works">
              See how answers are grounded <ArrowRight size={16} />
            </Link>
          </div>
        </section>

        {/* Workflow Section */}
        <section className="workflow-section">
          <div className="section section-wrap">
            <div className="workflow-heading">
              <div>
                <span className="eyebrow">THE RAG WORKFLOW</span>
                <h2>Retrieve first.<br /><span>Answer second.</span></h2>
              </div>
              <p>
                Dense embeddings, BM25 lexical search, cross-encoder reranking, and citation tracking ensure rock-solid answers.
              </p>
            </div>
            <div className="workflow-track workflow-track-six">
              {retrievalSteps.map(([number, title, text, Icon], index) => (
                <motion.div
                  className="workflow-step"
                  key={number}
                  initial={{ opacity: 0, y: 14 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.35 }}
                  transition={{ delay: index * 0.06 }}
                >
                  <div className="workflow-node"><Icon size={18} /></div>
                  <span className="step-number">{number}</span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                  {index < retrievalSteps.length - 1 && <span className="workflow-connector" aria-hidden="true" />}
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* BRIM Section */}
        <section className="section section-wrap brim-section">
          <div className="features-heading">
            <div>
              <span className="eyebrow">SAP + BRIM</span>
              <h2>Built for SAP.<br /><span>Deeply focused on BRIM.</span></h2>
            </div>
            <p>
              Full coverage across billing, rating, charging, subscription management, and financial accounts.
            </p>
          </div>
          <div className="feature-grid">
            {brimAreas.map(({ abbreviation, title, icon: Icon }, index) => (
              <motion.article
                className="feature-card brim-card"
                key={abbreviation}
                initial={{ opacity: 0, y: 14 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, amount: 0.25 }}
                transition={{ delay: index * 0.05 }}
              >
                <span className="feature-icon"><Icon size={19} strokeWidth={1.7} /></span>
                <span className="brim-abbreviation">{abbreviation}</span>
                <h3>{title}</h3>
                <span className="feature-card-line" />
              </motion.article>
            ))}
          </div>
        </section>

        {/* Response Preview */}
        <section className="response-section section section-wrap">
          <div className="response-copy">
            <span className="eyebrow">SOURCES + CONFIDENCE</span>
            <h2>Don't just get an answer.<br /><span>See what supports it.</span></h2>
            <p>
              Clyptusap.ai provides clickable sources, grounding score badges, and page citations alongside each response.
            </p>
          </div>
          <ResponsePreview />
        </section>

        {/* Boundary Section */}
        <section className="boundary-section">
          <div className="section section-wrap boundary-grid">
            <article className="boundary-card">
              <span className="eyebrow">WHEN KNOWLEDGE IS INSUFFICIENT</span>
              <h2>When the knowledge isn't there,<br /><span>Clyptusap.ai says so.</span></h2>
              <p>
                When retrieved documentation does not sufficiently support an answer, the assistant refuses to hallucinate invented settings or transaction codes.
              </p>
              <div className="boundary-example">
                <strong>User</strong>
                <p>“What is posting area 9999 used for in FI-CA?”</p>
                <strong>Assistant</strong>
                <p>“I couldn't find sufficient information in verified SAP documentation to answer this reliably.”</p>
              </div>
              <div className="boundary-tags">
                <span>Grounding Verification</span>
                <span>Verified Citations</span>
                <span>Zero Hallucination</span>
              </div>
            </article>

            <article className="boundary-card domain-card">
              <span className="eyebrow">DOMAIN BOUNDARY</span>
              <h2>Focused<br /><span>by design.</span></h2>
              <p>
                Clyptusap.ai is strictly specialized in SAP ERP, S/4HANA, Fiori, ABAP, Basis, and BRIM. General non-enterprise queries are rejected at pre-flight.
              </p>
              <div className="boundary-example">
                <strong>User</strong>
                <p>“What is the weather in Paris?”</p>
                <strong>Assistant</strong>
                <p>“I am strictly specialized in SAP and SAP BRIM enterprise systems. Please ask an SAP-related question.”</p>
              </div>
            </article>
          </div>
        </section>

        {/* Question Section */}
        <section className="section section-wrap question-section">
          <div className="question-heading">
            <span className="eyebrow">START WITH WHAT YOU'RE WORKING ON</span>
            <h2>Ask the SAP question<br /><span>already in front of you.</span></h2>
            <p>
              Ask about transaction codes, error messages, customizing paths, process integration, or configuration guidelines.
            </p>
          </div>
          <div className="question-list">
            {exampleQuestions.map((question, index) => (
              <div className="question-chip" key={question}>
                <span>0{index + 1}</span>
                <p>{question}</p>
                <ArrowUpRight size={15} />
              </div>
            ))}
          </div>
        </section>

        {/* About Clyptus Section */}
        <section id="about" className="about-clyptus-section section-wrap">
          <div className="about-clyptus-inner">
            <div className="about-header">
              <span className="eyebrow">ABOUT CLYPTUS &amp; CLYPTUSAP.AI</span>
              <h2>
                Engineered for enterprise precision.<br />
                <span>Zero guesswork in mission-critical SAP.</span>
              </h2>
              <p className="about-lead">
                Clyptus Technologies builds domain-specialized artificial intelligence systems designed strictly for complex ERP environments. Clyptusap.ai bridges the gap between massive, distributed SAP technical documentation and immediate, grounded decision-making for enterprise architects, billing consultants, and engineering teams.
              </p>
            </div>

            <div className="about-story-grid">
              <div className="about-story-card">
                <span className="story-badge">THE CHALLENGE</span>
                <h3>Why Generic AI Fails in SAP</h3>
                <p>
                  Standard large language models hallucinate non-existent transaction codes, invent fictitious SPRO customizing paths, and confuse SAP Convergent Charging rating logic with Convergent Invoicing billing plans. In high-throughput telecommunications, utilities, and subscription businesses, a single billing configuration error can delay millions in revenue recognition.
                </p>
              </div>

              <div className="about-story-card highlight-card">
                <span className="story-badge">THE CLYPTUS APPROACH</span>
                <h3>Grounding Before Generation</h3>
                <p>
                  Clyptusap.ai never relies on raw parametric memory for configuration paths or technical syntax. Every query triggers dense embedding retrieval combined with BM25 exact keyword matching, cross-encoder neural reranking, and mathematical grounding verification. If verified enterprise documentation doesn't back the answer, the system refuses rather than guessing.
                </p>
              </div>
            </div>

            <div className="about-pillars-grid">
              <div className="pillar-item">
                <div className="pillar-num">01</div>
                <h4>Authoritative Ingestion</h4>
                <p>Curated indexing of official SAP configuration guides, customizing dictionaries, master data schemas, and implementation blueprints.</p>
              </div>

              <div className="pillar-item">
                <div className="pillar-num">02</div>
                <h4>Dual-Stage Reranking</h4>
                <p>Cross-encoder neural models re-evaluate candidate chunks against the specific functional query before generation begins.</p>
              </div>

              <div className="pillar-item">
                <div className="pillar-num">03</div>
                <h4>Verifiable Citations</h4>
                <p>Every response displays clickable citations with document names, section paths, exact page numbers, and cosine similarity scores.</p>
              </div>

              <div className="pillar-item">
                <div className="pillar-num">04</div>
                <h4>Strict Tenant Isolation</h4>
                <p>Enterprise-grade security with JWT token authorization, project workspace grouping, and absolute confidentiality.</p>
              </div>
            </div>

            <div className="about-stats-band">
              <div className="stat-box">
                <strong>100%</strong>
                <span>Grounded Citations</span>
              </div>
              <div className="stat-box">
                <strong>5 Core</strong>
                <span>BRIM Modules Covered</span>
              </div>
              <div className="stat-box">
                <strong>&lt; 250ms</strong>
                <span>Neural Rerank Latency</span>
              </div>
              <div className="stat-box">
                <strong>Zero</strong>
                <span>Invented Configurations</span>
              </div>
            </div>
          </div>
        </section>

        {/* Use Cases */}
        <section className="usecase-section">
          <div className="section section-wrap">
            <div className="usecase-heading">
              <span className="eyebrow">SAP-SPECIFIC USE CASES</span>
              <h2>From questions<br /><span>to actionable technical clarity.</span></h2>
            </div>
            <div className="usecase-grid">
              {useCases.map(([title, text], i) => (
                <article key={title} className="usecase-card">
                  <span>0{i + 1}</span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ Section */}
        <FaqSection />

        {/* Final CTA */}
        <section className="final-cta section-wrap">
          <div className="final-cta-inner">
            <span className="eyebrow">READY TO EXPLORE SAP?</span>
            <h2>Have an SAP question?<br /><span>Ask Clyptusap.ai.</span></h2>
            <p>
              Get grounded answers across SAP and BRIM, backed by retrieved knowledge, sources and confidence.
            </p>
            <Link className="button button-brand" to="/login">
              Open Workspace <ArrowUpRight size={17} />
            </Link>
          </div>
        </section>
      </main>
      <Footer />
    </>
  );
};
