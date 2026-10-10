import React from 'react';
import { Link } from 'react-router-dom';
import fullLogoWhite from '../../assets/clyptusap-logo.png';
import fullLogoDark from '../../assets/clyptusap-logo-darktext.png';
import iconOnly from '../../assets/clyptusap-icon.png';

interface BrandLogoProps {
  compact?: boolean;
  light?: boolean;
}

export const BrandLogo: React.FC<BrandLogoProps> = ({ compact = false, light = false }) => {
  if (compact) {
    return (
      <Link className="brand inline-flex items-center" to="/" aria-label="Clyptusap.ai home">
        <img className="h-8 w-8 object-contain drop-shadow-sm" src={iconOnly} alt="Clyptusap.ai" />
      </Link>
    );
  }

  return (
    <Link className={`brand inline-flex items-center gap-2.5 ${light ? 'brand-light' : ''}`} to="/" aria-label="Clyptusap.ai home">
      {/* On dark surfaces show white text version; on light surfaces show dark text version */}
      <img
        className="h-8 w-auto object-contain dark:hidden"
        src={fullLogoDark}
        alt="Clyptusap.ai"
      />
      <img
        className="h-8 w-auto object-contain hidden dark:block"
        src={fullLogoWhite}
        alt="Clyptusap.ai"
      />
    </Link>
  );
};
