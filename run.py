"""Pipeline entry point — channel-aware.

Usage:
    python run.py                                  # render the World-stats channel
    python run.py --channel world                  # explicit
    python run.py --channel sports                 # render the Sports-stats channel
    python run.py --refetch                        # re-download source + assets
    python run.py --validate-layout                # print column bounds and exit
    python run.py --extract-movers                 # write cache/big_movers.json (world only)
    python run.py --generate-script                # narration script only (no TTS)
    python run.py --generate-narration             # script + ElevenLabs TTS
    python run.py --generate-variants              # one variant per beat → cache/variants.json
    python run.py --regenerate-section hook|middle|ending
    python run.py --auto-assemble                  # narration.json from variants (source=auto)
    python run.py --mux-narration                  # mux narration.wav onto rendered mp4
    python run.py --per-capita / --no-per-capita   # world only
    python run.py --accumulated / --no-accumulated # world only
    python run.py --preview-frame YEAR             # single PNG preview
    python run.py --preview-frames auto|y1,y2,...  # multi-frame preview
"""

import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env')
except ImportError:
    pass


CHANNEL_DEFAULTS = {
    'world':  {'config': 'config.json'},
    'sports': {'config': 'sportstatsraces/config.json'},
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--channel', choices=['world', 'sports'], default='world',
                   help='Which channel to render (default: world)')
    p.add_argument('--config', default=None,
                   help='Override the channel default config path')
    p.add_argument('--refetch', action='store_true',
                   help='Re-fetch source data (world only)')
    p.add_argument('--validate-layout', action='store_true')
    p.add_argument('--extract-movers', action='store_true',
                   help='Extract big-mover candidates (world only)')
    p.add_argument('--generate-script', action='store_true')
    p.add_argument('--generate-narration', action='store_true')
    p.add_argument('--mux-narration', action='store_true')
    p.add_argument('--generate-variants', action='store_true')
    p.add_argument('--regenerate-section',
                   choices=['hook', 'middle', 'ending'], default=None)
    p.add_argument('--auto-assemble', action='store_true',
                   help='Pick variant 0 from each section, write narration.json (source=auto)')
    p.add_argument('--per-capita', dest='per_capita',
                   action='store_true', default=None)
    p.add_argument('--no-per-capita', dest='per_capita',
                   action='store_false', default=None)
    p.add_argument('--accumulated', dest='accumulated',
                   action='store_true', default=None)
    p.add_argument('--no-accumulated', dest='accumulated',
                   action='store_false', default=None)
    p.add_argument('--preview-frame', type=float, default=None)
    p.add_argument('--preview-frames', type=str, default=None)
    args = p.parse_args()

    preview_frames = None
    if args.preview_frames is not None:
        s = args.preview_frames.strip()
        preview_frames = ('auto' if s.lower() == 'auto'
                          else [float(y) for y in s.split(',') if y.strip()])

    cfg_path = Path(args.config or CHANNEL_DEFAULTS[args.channel]['config']).resolve()

    if args.channel == 'world':
        from races.pipeline import run
        run(cfg_path,
            refetch=args.refetch,
            validate_layout=args.validate_layout,
            extract_movers=args.extract_movers,
            generate_script=args.generate_script,
            generate_narration=args.generate_narration,
            mux_narration=args.mux_narration,
            generate_variants=args.generate_variants,
            regenerate_section=args.regenerate_section,
            auto_assemble=args.auto_assemble,
            per_capita_override=args.per_capita,
            accumulated_override=args.accumulated,
            preview_frame_year=args.preview_frame,
            preview_frame_years=preview_frames)
    else:
        # Importing the package mutates source/asset registries to add
        # fbref_pl + headshots before the pipeline builds them.
        import sportstatsraces  # noqa: F401
        from sportstatsraces.pipeline import run
        run(cfg_path,
            validate_layout=args.validate_layout,
            preview_frame_year=args.preview_frame,
            preview_frame_years=preview_frames)


if __name__ == '__main__':
    main()
