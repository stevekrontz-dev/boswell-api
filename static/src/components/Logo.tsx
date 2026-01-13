interface LogoProps {
  size?: 'sm' | 'md' | 'lg';
  showText?: boolean;
}

export default function Logo({ size = 'md', showText = false }: LogoProps) {
  const sizes = {
    sm: 'w-8 h-8',
    md: 'w-10 h-10',
    lg: 'w-14 h-14',
  };

  const textSizes = {
    sm: 'text-lg',
    md: 'text-xl',
    lg: 'text-2xl',
  };

  return (
    <div className="flex items-center gap-3">
      {/* Circular monogram logo matching askboswell.com */}
      <div className={`${sizes[size]} relative`}>
        <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
          {/* Outer decorative ring */}
          <circle cx="20" cy="20" r="19" stroke="#f97316" strokeWidth="1" opacity="0.6" />
          {/* Inner circle */}
          <circle cx="20" cy="20" r="16" stroke="#f97316" strokeWidth="1.5" />
          {/* B monogram */}
          <text
            x="20"
            y="26"
            textAnchor="middle"
            fill="#f97316"
            fontFamily="'Playfair Display', Georgia, serif"
            fontSize="18"
            fontWeight="500"
          >
            B
          </text>
        </svg>
      </div>
      {showText && (
        <span className={`font-display font-medium text-ember-500 ${textSizes[size]}`}>
          Boswell
        </span>
      )}
    </div>
  );
}
