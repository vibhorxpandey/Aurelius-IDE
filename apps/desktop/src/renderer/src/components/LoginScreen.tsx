import { useState } from "react";
import type { UserProfile } from "../state/profile";
import { LogoMark } from "./icons";

interface LoginScreenProps {
  onContinue: (profile: UserProfile) => void;
}

/**
 * Gates entry to the workspace. Framed honestly: this is a local display identity for a
 * prototype with no backend, not an authentication system — hence no password field and
 * no branded third-party sign-in buttons that would misrepresent what's actually happening.
 */
export default function LoginScreen({ onContinue }: LoginScreenProps) {
  const [name, setName] = useState("");
  const [institution, setInstitution] = useState("");
  const [email, setEmail] = useState("");
  const [touched, setTouched] = useState(false);

  const nameValid = name.trim().length > 1;

  const submit = () => {
    setTouched(true);
    if (!nameValid) return;
    onContinue({
      name: name.trim(),
      institution: institution.trim(),
      email: email.trim(),
      joinedAt: new Date().toISOString(),
    });
  };

  return (
    <div className="login">
      <div className="login__card">
        <div className="login__logo">
          <LogoMark size={30} />
          <span>Aurelius</span>
        </div>
        <p className="login__tagline">A language server for research papers.</p>

        <label className="login__field">
          <span>Name</span>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="Jane Researcher"
          />
          {touched && !nameValid && <span className="login__error">Enter your name to continue.</span>}
        </label>

        <label className="login__field">
          <span>Institution (optional)</span>
          <input
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="University or lab"
          />
        </label>

        <label className="login__field">
          <span>Email (optional)</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
            placeholder="jane@university.edu"
          />
        </label>

        <button className="login__submit" onClick={submit}>
          Continue to Aurelius
        </button>

        <p className="login__note">
          This is a local profile for the prototype — nothing here is sent anywhere or
          checked against a password. It just personalises the workspace and is stored on
          this machine.
        </p>
      </div>
    </div>
  );
}
