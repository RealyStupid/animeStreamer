import Link from "next/link";
import Image from "next/image";

// 1. Define your navigation links in one place
const navLinks = [
  { href: "/", label: "Home" },
  { href: "/trending", label: "Trending" },
  { href: "/Aboutus", label: "About Us" },
];

export default function Nav() {
  return (
    <nav className="nav">
      {/* Brand Logo & Name */}
      <Link href="/" className="nav-logo">
        {/* temporary logo, change LATER */}
        <Image src="/globe.svg" alt="PiraTube Logo" width={32} height={32} loading="eager"/>
        <span className="text-xl font-bold text-red-500">PiraTube</span>
      </Link>

      {/* Navigation Links */}
      <ul className="nav-links">
        {navLinks.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className="text-sm font-medium text-neutral-300 hover:text-white transition-colors"
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>

      {/* Action Buttons */}
      <div className="flex items-center gap-3">
        <Link
          href="/login"
          className="text-sm font-medium text-neutral-300 hover:text-white transition-colors px-3 py-1.5"
        >
          Login
        </Link>
        <Link
          href="/register"
          className="text-sm font-medium bg-red-600 hover:bg-red-700 text-white px-3.5 py-3 rounded-md transition-colors"
        >
          Sign Up
        </Link>
      </div>
    </nav>
  );
}