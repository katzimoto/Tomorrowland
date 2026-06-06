/* global React, Button, TextInput */

function SignIn({ onSignIn, expired }) {
  const [email, setEmail] = React.useState("ops@acme.local");
  const [password, setPassword] = React.useState("•••••••••");
  const [pending, setPending] = React.useState(false);

  function submit(e) {
    e?.preventDefault();
    setPending(true);
    setTimeout(() => {
      setPending(false);
      onSignIn?.({ email });
    }, 500);
  }

  return (
    <div className="login-page" data-screen-label="Sign in">
      <div className="login-card">
        <img className="login-mark" src="../../assets/favicon.svg" alt="Tomorrowland logo" />
        <h1 className="login-heading">Sign in to Tomorrowland</h1>

        {expired && (
          <p className="login-alert" role="alert">
            Your session expired. Sign in again.
          </p>
        )}

        <form className="login-form" onSubmit={submit} noValidate>
          <TextInput
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={setEmail}
            autoFocus
          />
          <TextInput
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={setPassword}
          />
          <Button type="submit" loading={pending} style={{ width: "100%" }}>
            Sign in
          </Button>
        </form>

        <p className="login-switch">
          <a>Don't have an account? Sign up</a>
        </p>

        <div className="login-lang-row">
          <select defaultValue="en">
            <option value="en">English</option>
            <option value="he">עברית</option>
          </select>
        </div>
      </div>
    </div>
  );
}

window.SignIn = SignIn;
