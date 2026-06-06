interface TomorrowlandLogoProps {
  size?: number;
  className?: string;
}

export function TomorrowlandLogo({ size = 40, className }: TomorrowlandLogoProps) {
  return (
    <img
      src="/tomorrowland-logo-cyber-bike.svg"
      alt="Tomorrowland logo"
      width={size}
      height={size}
      className={className}
      style={{ display: "block", objectFit: "contain", flexShrink: 0 }}
    />
  );
}
