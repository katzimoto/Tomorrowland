/* global React, Icon */
// Stateless visual primitives — mirror frontend/src/components/primitives/*.

// ---------- Button ----------
function Button({ variant = "primary", size = "md", loading, disabled, children, onClick, type = "button", style }) {
  const cls = ["btn", `btn-${variant}`];
  if (size === "sm") cls.push("btn-sm");
  return (
    <button
      type={type}
      className={cls.join(" ")}
      disabled={disabled || loading}
      onClick={onClick}
      style={style}
    >
      {loading ? <span className="btn-spinner" /> : null}
      {children}
    </button>
  );
}

// ---------- Badge ----------
function Badge({ variant = "neutral", children }) {
  return <span className={`badge ${variant}`}>{children}</span>;
}

// ---------- TextInput ----------
function TextInput({ label, type = "text", value, onChange, error, autoFocus, autoComplete, placeholder }) {
  return (
    <div className="field">
      {label && <label className="field-label">{label}</label>}
      <input
        type={type}
        className={`text-input${error ? " error" : ""}`}
        value={value || ""}
        onChange={(e) => onChange?.(e.target.value)}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        placeholder={placeholder}
      />
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}

// ---------- SearchInput ----------
const SearchInput = React.forwardRef(function SearchInput(
  { value, onChange, onSubmit, placeholder = "Search documents…", autoFocus },
  ref,
) {
  return (
    <div className="search-input">
      <span className="icn"><Icon name="search" size={16} /></span>
      <input
        ref={ref}
        type="search"
        value={value || ""}
        onChange={(e) => onChange?.(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") onSubmit?.(); }}
        placeholder={placeholder}
        autoFocus={autoFocus}
      />
    </div>
  );
});

Object.assign(window, { Button, Badge, TextInput, SearchInput });
