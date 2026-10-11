import Link from "next/link"

export default function LandingHead() {
    return (
        <main className="relative overflow-hidden">
            {/* Background Glow */}
            <div className="absolute inset-0 bg-[#191919]" />
            <section className="relative flex flex-col items-center justify-center text-center pb-10 px-6 py-25">
                <h1 className="text-7xl md:text-8xl font-extrabold">
                    Welcome To
                    <span className="text-red-600"> AnimeWatcher</span>
                </h1>

                <p className="mt-6 max-w-2xl text-xl text-gray-500">
                    Stream movies, anime, shows, and other content across seas! <br />
                    Fast, free, and most importantly: no subscription!
                </p>

                <div className="flex flex-wrap justify-center gap-4 mt-8">
                    <Link
                        href="/register"
                        className="px-8 py-4 rounded-xl bg-red-600 hover:bg-red-700 transition font-semibold text-white shadow-lg shadow-red-600/20"
                    >
                        Create An Account
                    </Link>

                    <Link
                        href="/browse"
                        className="px-8 py-4 rounded-xl border border-gray-700 hover:border-gray-500 transition font-medium text-gray-300"
                    >
                        Browse Library
                    </Link>
                </div>
            </section>
        </main>
    )
}