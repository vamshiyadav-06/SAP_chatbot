import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { BrandLogo } from '../navbar/BrandLogo';

export const Footer: React.FC = () => {
  return (
    <footer className="footer">
      <div className="footer-main">
        <div>
          <BrandLogo />
          <p>
            SAP knowledge, retrieved<br />for clearer answers.
          </p>
        </div>
        <div className="footer-links">
          <span>EXPLORE</span>
          <Link to="/features">Features</Link>
          <Link to="/how-it-works">How it works</Link>
          <a href="/#about">About Clyptus</a>
          <a href="/#faq">FAQ</a>
        </div>
        <div className="footer-links">
          <span>GET STARTED</span>
          <Link to="/login">Sign in</Link>
          <Link to="/login">Ask Clyptusap.ai <ArrowUpRight size={14} /></Link>
        </div>
      </div>
      <div className="footer-bottom">
        <span>© {new Date().getFullYear()} Clyptusap.ai</span>
        <span>SAP-focused · RAG-powered · Grounded in retrieved knowledge</span>
      </div>
    </footer>
  );
};
