import React from 'react';
import { Plus } from 'lucide-react';

const faqs = [
  ['What is Clyptusap.ai?', 'Clyptusap.ai is an AI-powered SAP knowledge assistant. It retrieves relevant indexed knowledge before generating an answer, with a dedicated focus on SAP BRIM.'],
  ['What does “RAG-powered” mean?', 'Retrieval-Augmented Generation retrieves relevant SAP knowledge and provides it as context to an AI model before it generates an answer.'],
  ['Which SAP BRIM areas does it support?', 'Its BRIM focus includes Convergent Mediation (CM), Convergent Charging (CC), Convergent Invoicing (CI), FI-CA, and Subscription Order Management (SOM).'],
  ['Can I see sources and confidence?', 'Supporting sources and confidence or grounding information are shown with every response. Citations link directly to verified documentation chunks.'],
  ['How does generation work?', 'The assistant streams responses token-by-token with real-time thinking status indicators and grounding verification.'],
  ['What if the available knowledge cannot answer?', 'The assistant strictly respects enterprise domain boundaries, declining out-of-scope non-SAP requests and alerting when knowledge is insufficient.'],
];

export const FaqSection: React.FC = () => {
  return (
    <section className="section faq-section" id="faq">
      <div className="section-heading">
        <span className="eyebrow">A FEW GOOD QUESTIONS</span>
        <h2>Curious? <span>We thought so.</span></h2>
      </div>
      <div className="faq-list">
        {faqs.map(([question, answer]) => (
          <details className="faq-item" key={question}>
            <summary>
              {question}
              <Plus size={18} aria-hidden="true" />
            </summary>
            <p>{answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
};
