export default function LandingHead() {
    return (
        <main className="relative overflow-hidden">
            {/* Background Glow */}
            <div className="absolute inset-0 bg-[#191919]" />
            <section className="relative flex flex-col items-center justify-center text-center pb-10 px-6 pt-25">
                <h1 className="text-7xl md:text-8x1 font-extrabold">
                    Welcome To
                    <span className="text-red-600"> PiraTube</span>
                </h1>

                <p className="mt-6 max-w-2xl text-xl text-gray-500">
                    Stream movies, anime, shows, and other content across seas! <br />
                    Fast, free, and most importantly: no subscription!
                </p>

                <div className="flex gap-6 mt-5">
                    <button className="px-8 py-4 rounded-xl bg-red-500 hover:bg-red-400 transition font-semibold">
                        Create An Account
                    </button>

                    <button className="px-8 py-4 rounded-xl border border-gray-700 hover:border-gray-400 transition">
                        Browse Library
                    </button>
                </div>
            </section>
        </main>
    )
}