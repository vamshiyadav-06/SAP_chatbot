import React from 'react';
import { Plus } from 'lucide-react';

const faqs: Array<[string, React.ReactNode]> = [
  ['What is Clyptus.AI?', <><strong>Clyptus.AI</strong> is an AI knowledge assistant for SAP, with a dedicated focus on <strong>SAP BRIM</strong>: Subscription Order Management, Convergent Charging, Convergent Invoicing, FI-CA and Convergent Mediation.</>],
  ['What is the difference between Low and High?', <>Every chat starts in <strong>Low</strong>, which answers directly from the language model and streams as it writes, which suits quick questions. Press the <strong>High ↑</strong> button in the chat box and it retrieves from the SAP knowledge base first, verifies the draft against that evidence, and only then shows the answer. It takes longer and is better for configuration, integration and troubleshooting questions. Press the button again to go back to Low.</>],
  ['What does “retrieval-augmented generation” mean?', <><strong>Retrieval-augmented generation (RAG)</strong> finds relevant documentation first and gives it to the model as context, so the answer is based on sources rather than on the model's memory alone. High adds a <strong>claim-level grounding check</strong> on top, which greatly reduces invented details.</>],
  ['Where do High answers come from?', <>From an <strong>administrator-curated knowledge base</strong> of SAP documentation. When internal evidence is weak, High can also search <strong>approved SAP sources</strong> such as SAP Help Portal, SAP Community and SAP Learning.</>],
  ['Does it remember earlier messages?', <>Yes, in both modes. It uses the <strong>last 20 messages</strong>, a <strong>running summary</strong> of older turns, and can recall what you asked earlier in this chat or in your other chats. Your conversations are private to your account unless you share a prompt link.</>],
  ['Can I upload my own documents?', <>Yes. Attach <strong>PDF, Word, text or Markdown</strong> files to a message and ask about them. Uploaded text is used as context within that chat and is not added to the shared knowledge base.</>],
  ['Will I see the source documents?', <>Internal documents are <strong>managed and access-controlled by administrators</strong>. Regular users receive the verified answer and suggested follow-up questions; source excerpts and retrieval scores are available to administrators for review.</>],
  ['What if it cannot answer?', <>Questions outside SAP are <strong>declined up front</strong>. In High, if the evidence does not support an answer, it <strong>says so instead of guessing</strong>.</>],
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
