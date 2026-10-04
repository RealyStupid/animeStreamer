import Link from "next/link";
import Image from "next/image";

export default function Nav() {
    return (
        <nav className="nav">
            <Link href="/" className="flex flex-row items-center gap-2">
                <Image src="/globe.svg" alt="PiraTube Logo" width={32} height={32} />

                <span className="text-xl font-bold text-red-500">
                    PiraTube
                </span>
            </Link>
        </nav>
    );
}