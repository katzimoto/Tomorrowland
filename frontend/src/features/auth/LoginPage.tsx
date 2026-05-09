import { useNavigate, useSearch } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { login } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/primitives/Button";
import { TextInput } from "@/components/primitives/TextInput";
import styles from "./LoginPage.module.css";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
});

type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const navigate = useNavigate();
  const search = useSearch({ from: "/login" }) as { expired?: string; return?: string };

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit({ email, password }: FormValues) {
    try {
      await login(email, password);
      const returnTo = typeof search.return === "string" && search.return.startsWith("/")
        ? search.return
        : "/search";
      await navigate({ to: returnTo });
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 401
          ? "Email or password is incorrect."
          : "Something went wrong. Try again.";
      setError("root", { message });
    }
  }

  return (
    <div className={styles.page} aria-label="Sign in">
      <div className={styles.card}>
        <div className={styles.mark} aria-label="Neverland">N</div>
        <h1 className={styles.heading}>Sign in to Neverland</h1>

        {search.expired && (
          <p className={styles.alert} role="alert">
            Your session expired. Sign in again.
          </p>
        )}

        <form className={styles.form} onSubmit={handleSubmit(onSubmit)} noValidate>
          <TextInput
            label="Email"
            type="email"
            autoComplete="email"
            autoFocus
            error={errors.email?.message}
            {...register("email")}
          />
          <TextInput
            label="Password"
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

          <Button type="submit" loading={isSubmitting} style={{ width: "100%" }}>
            Sign in
          </Button>
        </form>
      </div>
    </div>
  );
}
