import { useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { signUp } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/primitives/Button";
import { TextInput } from "@/components/primitives/TextInput";
import { LanguageSelector } from "@/components/settings/LanguageSelector";
import { useT } from "@/i18n/index";
import { TomorrowlandLogo } from "@/components/brand/TomorrowlandLogo";
import styles from "./LoginPage.module.css";

function makeSchema(
  emailInvalid: string,
  passwordRequired: string,
  passwordMismatch: string,
) {
  return z
    .object({
      email: z.string().email(emailInvalid),
      displayName: z.string().optional(),
      password: z.string().min(1, passwordRequired),
      confirmPassword: z.string().min(1, passwordRequired),
    })
    .refine((data) => data.password === data.confirmPassword, {
      message: passwordMismatch,
      path: ["confirmPassword"],
    });
}

type FormValues = {
  email: string;
  displayName?: string;
  password: string;
  confirmPassword: string;
};

export function SignUpPage() {
  const t = useT();
  const navigate = useNavigate();

  const schema = makeSchema(
    t.auth.emailInvalid,
    t.auth.passwordRequired,
    t.auth.passwordMismatch,
  );

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit({ email, displayName, password }: FormValues) {
    try {
      await signUp(email, password, displayName || undefined);
      await navigate({ to: "/search", search: { q: "", mode: "hybrid" } });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("root", { message: t.auth.duplicateEmail });
      } else {
        setError("root", { message: t.auth.genericError });
      }
    }
  }

  return (
    <div className={styles.page} aria-label={t.auth.signUpTitle}>
      <div className={styles.card}>
        <TomorrowlandLogo size={40} className={styles.mark} />
        <h1 className={styles.heading}>{t.auth.signUpTitle}</h1>

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
            label={t.auth.displayName}
            type="text"
            autoComplete="name"
            error={errors.displayName?.message}
            {...register("displayName")}
          />
          <TextInput
            label={t.auth.password}
            type="password"
            autoComplete="new-password"
            error={errors.password?.message}
            {...register("password")}
          />
          <TextInput
            label={t.auth.confirmPassword}
            type="password"
            autoComplete="new-password"
            error={errors.confirmPassword?.message}
            {...register("confirmPassword")}
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
            {t.auth.signUp}
          </Button>
        </form>

        <p className={styles.switchLink}>
          <a href="/login">{t.auth.signInLink}</a>
        </p>

        <div className={styles.langRow}>
          <LanguageSelector />
        </div>
      </div>
    </div>
  );
}
