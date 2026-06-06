import { useNavigate, useSearch } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { login } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/primitives/Button";
import { TextInput } from "@/components/primitives/TextInput";
import { LanguageSelector } from "@/components/settings/LanguageSelector";
import { useT } from "@/i18n/index";
import { startNamedPerformanceTimer } from "@/lib/performanceTelemetry";
import { TomorrowlandLogo } from "@/components/brand/TomorrowlandLogo";
import styles from "./LoginPage.module.css";

function makeSchema(emailInvalid: string, passwordRequired: string) {
  return z.object({
    email: z.string().email(emailInvalid),
    password: z.string().min(1, passwordRequired),
  });
}

type FormValues = { email: string; password: string };

export function LoginPage() {
  const t = useT();
  const navigate = useNavigate();
  const search = useSearch({ from: "/login" }) as {
    expired?: string;
    return?: string;
  };

  const schema = makeSchema(t.auth.emailInvalid, t.auth.passwordRequired);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit({ email, password }: FormValues) {
    try {
      startNamedPerformanceTimer("login.shell");
      await login(email, password);
      const returnTo =
        typeof search.return === "string" && search.return.startsWith("/")
          ? search.return
          : "/search";
      await navigate({ to: returnTo });
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 401
          ? t.auth.badCredentials
          : t.auth.genericError;
      setError("root", { message });
    }
  }

  return (
    <div className={styles.page} aria-label={t.auth.signInLabel}>
      <div className={styles.card}>
        <TomorrowlandLogo size={40} className={styles.mark} />
        <h1 className={styles.heading}>{t.auth.heading}</h1>

        {search.expired && (
          <p className={styles.alert} role="alert">
            {t.auth.sessionExpired}
          </p>
        )}

        <form
          className={styles.form}
          onSubmit={handleSubmit(onSubmit)}
          noValidate
        >
          <TextInput
            label={t.auth.email}
            type="email"
            autoComplete="email"
            autoFocus
            error={errors.email?.message}
            {...register("email")}
          />
          <TextInput
            label={t.auth.password}
            type="password"
            autoComplete="current-password"
            error={errors.password?.message}
            {...register("password")}
          />

          {errors.root && (
            <p className={styles.rootError} role="alert">
              {errors.root.message}
            </p>
          )}

          <Button
            type="submit"
            loading={isSubmitting}
            style={{ width: "100%" }}
          >
            {t.auth.signIn}
          </Button>
        </form>

        <p className={styles.switchLink}>
          <a href="/signup">{t.auth.signUpLink}</a>
        </p>

        <div className={styles.langRow}>
          <LanguageSelector />
        </div>
      </div>
    </div>
  );
}
