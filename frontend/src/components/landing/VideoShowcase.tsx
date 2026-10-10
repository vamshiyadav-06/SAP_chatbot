import React from 'react';
import { ArrowUpRight, Search, ShieldCheck, Sparkles } from 'lucide-react';

export const VideoShowcase: React.FC = () => {
  return (
    <div className="showcase-frame">
      <div className="showcase-placeholder" aria-label="Product preview showcase">
        <div className="mock-window">
          <div className="mock-sidebar">
            <div className="mock-brand-dot"><span /></div>
            <div className="mock-nav-line active" />
            <div className="mock-nav-line" />
            <div className="mock-nav-line short" />
            <div className="mock-sidebar-bottom"><span /><span /></div>
          </div>
          <div className="mock-product">
            <div className="mock-product-top">
              <span>SAP + BRIM KNOWLEDGE</span>
              <span className="mock-avatar">C</span>
            </div>
            <div className="mock-product-body">
              <span className="mock-eyebrow">RETRIEVE FIRST. ANSWER SECOND.</span>
              <strong>Your SAP question,<br />with relevant context.</strong>
              <div className="mock-question">
                <Search size={15} />
                <span>Explain the BRIM billing flow</span>
                <ArrowUpRight size={15} />
              </div>
              <div className="mock-sources">
                <ShieldCheck size={14} />
                <span>Grounded answer</span>
                <i />
                <span>Sources when available</span>
              </div>
            </div>
            <div className="mock-preview-note">
              <Sparkles size={13} /> AI Enterprise Assistant
            </div>
          </div>
        </div>
        <p className="video-placeholder-caption">Interactive Clyptusap.ai workspace</p>
      </div>
      <div className="showcase-caption">
        <span className="live-dot" /> SAP + BRIM knowledge in action
        <span className="caption-arrow"><ArrowUpRight size={14} /></span>
      </div>
    </div>
  );
};
