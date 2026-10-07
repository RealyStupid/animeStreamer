import Link from "next/link";
import Image from "next/image";

// 1. Define your navigation links in one place
const navLinks = [
  { href: "/", label: "Home" },
  { href: "/trending", label: "Trending" },
  { href: "/Aboutus", label: "About Us" },
  { href: "/browse", label: "Browse"}
];

export default function Nav() {
  return (
    <nav className="nav">
      {/* Brand Logo & Name */}
      <Link href="/" className="nav-logo">
        {/* temporary logo, change LATER */}
        <Image src="/globe.svg" alt="PiraTube Logo" width={26} height={26} loading="eager"/>
        <span className="text-xl font-bold text-red-500">PiraTube</span>
      </Link>

      {/* Navigation Links */}
      <ul className="nav-links">
        {navLinks.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className="text-lg font-medium text-neutral-300 hover:text-white transition-colors"
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
          className="text-base font-medium text-neutral-300 hover:text-white transition-colors px-3 py-1.5"
        >
          Login
        </Link>
        <Link
          href="/register"
          className="text-base font-medium bg-red-600 hover:bg-red-700 text-white px-4.5 py-1.5 rounded-md transition-colors"
        >
          Sign Up
        </Link>
      </div>
    </nav>
  );
}