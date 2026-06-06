import styles from "./IconButton.module.css";

interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  size?: "sm" | "md";
  variant?: "ghost" | "secondary";
  children: React.ReactNode;
}

export function IconButton({
  label,
  size = "md",
  variant = "ghost",
  children,
  className = "",
  ...rest
}: IconButtonProps) {
  return (
    <button
      className={`${styles.btn} ${styles[size]} ${styles[variant]} ${className}`}
      aria-label={label}
      title={label}
      {...rest}
    >
      {children}
    </button>
  );
}
