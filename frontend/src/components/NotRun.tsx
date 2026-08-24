export default function NotRun({ title, command }: { title: string; command: string }) {
  return (
    <main className="browse-page rl-page">
      <header className="browse-header">
        <h1>{title}</h1>
        <p className="lede">This experiment has not been run in this checkout.</p>
      </header>
      <div className="card rl-note">
        Run <code>{command}</code>, then <code>make dashboard</code> to populate this view.
      </div>
    </main>
  );
}
