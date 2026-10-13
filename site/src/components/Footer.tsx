import Link from "next/link";

export default function Footer() {
  return (
    <footer className="border-t border-neutral-800 bg-[#151515] px-5 py-8 text-neutral-400">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <Link
          className="w-fit text-sm font-bold tracking-wide text-white transition hover:text-red-400"
          href="/"
        >
          AnimeWatcher
        </Link>
        <nav aria-label="Footer" className="flex flex-wrap gap-x-6 gap-y-2">
          <Link className="text-sm transition hover:text-white" href="/browse">
            Browse
          </Link>
          <Link className="text-sm transition hover:text-white" href="/profile">
            Profile
          </Link>
        </nav>
        <p className="text-xs">Find your next favorite.</p>
      </div>
    </footer>
  );
}
