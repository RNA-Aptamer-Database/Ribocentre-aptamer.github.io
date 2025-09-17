#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export annotated mmCIF files for aptamers that have 3D viewer configs.

For each aptamer with a local/remote PDB id, this script attempts to
produce two files under apidata/colored_structures/<slug>/:
  - <pdb_id>.cif              (downloaded from RCSB if not present locally)
  - <pdb_id>.annotated.cif   (same content with a header comment block
                              embedding JSON color rules)
And writes/updates apidata/colored_structures/index.json to include
the mmCIF paths.

Usage:
  python scripts/export_mmcif_with_annotations.py \
    --merged apidata/merged_data_0907.json \
    --output apidata/colored_structures [--single Hfq-aptamer]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from datetime import datetime
from zipfile import ZipFile, ZIP_DEFLATED
import socket
import time
import gzip
from io import BytesIO


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def guess_pdb_id_from_path(p: str) -> str | None:
    # extract 4-char PDB id from filename tokens
    name = Path(p).name
    m = re.search(r'([0-9][A-Za-z0-9]{3})', name)
    if m:
        return m.group(1).upper()
    return None


def _http_get(url: str, timeout: int) -> bytes:
    req = Request(url, headers={'User-Agent': 'Ribocentre-aptamer-export/1.0'})
    with urlopen(req, timeout=timeout) as resp:
        # Stream in chunks to avoid long single-read stuck
        chunks = []
        while True:
            chunk = resp.read(1024 * 64)
            if not chunk:
                break
            chunks.append(chunk)
        return b''.join(chunks)


def download_cif(pdb_id: str, timeout: int = 45, retries: int = 3, retry_delay: float = 2.0) -> bytes:
    """Download mmCIF for a PDB ID with retries.

    Tries .cif first, then .cif.gz fallback. Raises on final failure.
    """
    last_err = None
    urls = [
        f'https://files.rcsb.org/download/{pdb_id}.cif',
        f'https://files.rcsb.org/download/{pdb_id}.cif.gz',
    ]
    for attempt in range(1, retries + 1):
        for u in urls:
            try:
                data = _http_get(u, timeout)
                if u.endswith('.gz'):
                    try:
                        data = gzip.decompress(data)
                    except OSError:
                        # Some servers might already send plain text
                        pass
                return data
            except (TimeoutError, socket.timeout) as e:
                last_err = e
            except (URLError, HTTPError, OSError) as e:
                last_err = e
        if attempt < retries:
            time.sleep(retry_delay * attempt)  # backoff
    # On failure
    if last_err:
        raise last_err
    raise RuntimeError(f'Failed to download CIF for {pdb_id} after {retries} retries')


def load_local_cif(repo_root: Path, pdb_id: str) -> bytes | None:
    # Try common local locations
    pdb_dir = repo_root / 'pdbfiles'
    candidates = [
        pdb_dir / f'{pdb_id}.cif',
        pdb_dir / f'{pdb_id.upper()}.cif',
        pdb_dir / f'{pdb_id.lower()}.cif',
    ]
    for c in candidates:
        if c.exists():
            return c.read_bytes()
    return None


def annotate_cif(cif_text: str, slug: str, title: str | None, color_schemes) -> str:
    """Annotate mmCIF with a human-readable color matrix.

    The annotation is added as comment lines at the top of the CIF file.
    Two tables are provided for readability:
      1) color_ranges: chain,start,end,r,g,b
      2) color_residues: chain,residue,r,g,b (expanded per residue)
    """
    header_lines: list[str] = []
    header_lines.append('# Ribocentre Aptamer Colored Structure Annotation')
    header_lines.append('# version: 2')
    header_lines.append(f'# slug: {slug}')
    header_lines.append(f'# title: {title or ""}')

    # Normalize color schemes
    ranges = []  # list of (chain, start, end, r,g,b)
    residues = []  # list of (chain, resno, r,g,b)
    if isinstance(color_schemes, list):
        for rule in color_schemes:
            if not isinstance(rule, dict):
                continue
            chain = rule.get('struct_asym_id')
            start = rule.get('start_residue_number')
            end = rule.get('end_residue_number')
            col = rule.get('color') or {}
            try:
                r = int(col.get('r'))
                g = int(col.get('g'))
                b = int(col.get('b'))
            except Exception:
                # Skip rules without valid color
                continue
            try:
                start_i = int(start)
                end_i = int(end)
            except Exception:
                # If any bound missing, treat as a single residue if possible
                try:
                    single = int(start if start is not None else end)
                except Exception:
                    continue
                if chain:
                    ranges.append((chain, single, single, r, g, b))
                    residues.append((chain, single, r, g, b))
                continue

            if not chain:
                continue
            if end_i < start_i:
                start_i, end_i = end_i, start_i
            ranges.append((chain, start_i, end_i, r, g, b))
            # Expand to per-residue entries for readability
            for resno in range(start_i, end_i + 1):
                residues.append((chain, resno, r, g, b))

    # Emit compact range table
    header_lines.append('# annotation.color_ranges (columns: chain,start,end,r,g,b)')
    if ranges:
        for chain, start_i, end_i, r, g, b in ranges:
            header_lines.append(f'# {chain},{start_i},{end_i},{r},{g},{b}')
    else:
        header_lines.append('# (no ranges)')

    # Emit per-residue matrix
    header_lines.append('# annotation.color_residues (columns: chain,residue,r,g,b)')
    if residues:
        for chain, resno, r, g, b in residues:
            header_lines.append(f'# {chain},{resno},{r},{g},{b}')
    else:
        header_lines.append('# (no residues)')

    header_lines.append('# end_annotation')
    return '\n'.join(header_lines) + '\n' + cif_text


def main():
    ap = argparse.ArgumentParser(description='导出带注释的 mmCIF 文件（支持多结构/合并）')
    ap.add_argument('--merged', default='apidata/merged_data_0907.json', help='合并数据 JSON 路径')
    ap.add_argument('--output', default='apidata/colored_structures', help='输出目录（会生成各 aptamer 子目录）')
    ap.add_argument('--single', help='仅处理指定 slug（例如 eIF4A-aptamer）')
    ap.add_argument('--offline', action='store_true', help='离线模式：只注释本地已有 CIF，不联网下载')
    ap.add_argument('--net-timeout', type=int, default=60, help='联网下载超时（秒）')
    ap.add_argument('--net-retries', type=int, default=4, help='联网下载重试次数')
    ap.add_argument('--retry-delay', type=float, default=2.0, help='重试增量间隔（秒）')
    ap.add_argument('--verbose', action='store_true', help='输出详细调试日志')
    ap.add_argument('--fallback-summary', action='store_true', help='页面无 PDB 时，回退使用结构汇总的首个 ID')
    ap.add_argument('--overrides', help='覆盖文件：{ slug: pdb_id | [pdb_id] | {composite:[{pdb_id,chain_map?}], mode?} }')
    ap.add_argument('--prompt-missing', action='store_true', help='页面缺少 ID 时，交互式输入（支持链映射 1XWP A>C）')
    ap.add_argument('--save-overrides', help='与 --prompt-missing 配合：将选择保存到该 JSON 以便复用')
    ap.add_argument('--prompt-augment', action='store_true', help='即便已检测到单个 ID，也允许在交互中追加更多')
    ap.add_argument('--multi-mode', choices=['separate', 'merge'], default='separate', help='多结构时：分别输出或额外生成合并文件')
    ap.add_argument('--merge-engine', choices=['auto', 'pymol', 'gemmi', 'concat'], default='auto', help='合并引擎：优先 PyMOL，其次 gemmi，最后文本拼接')
    args = ap.parse_args()

    repo_root = Path.cwd()
    merged = read_json(Path(args.merged))
    aptamers = merged.get('aptamers', {})
    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)

    # Load or init index.json
    index_path = out_root / 'index.json'
    if index_path.exists():
        index = read_json(index_path)
    else:
        index = {'generated_at': None, 'source': args.merged, 'total': 0, 'items': []}

    items_by_slug = {it.get('slug'): it for it in index.get('items', []) if isinstance(it, dict)}

    overrides = {}
    if args.overrides:
        try:
            p = Path(args.overrides)
            if p.exists():
                overrides = read_json(p) or {}
                if args.verbose:
                    print(f'Loaded overrides: {list(overrides.keys())[:5]}...')
        except Exception as e:
            if args.verbose:
                print(f'WARN failed to load overrides {args.overrides}: {e}')
    # If user wants to persist prompted choices but provided no existing overrides path, use save-overrides
    if not args.overrides and args.save_overrides:
        # ensure directory exists; file may not exist yet
        Path(args.save_overrides).parent.mkdir(parents=True, exist_ok=True)

    def is_valid_pdb_id(s: str | None) -> bool:
        return isinstance(s, str) and bool(re.fullmatch(r'[0-9][A-Za-z0-9]{3}', s.strip()))

    def parse_composite_input(text: str):
        """Parse user input for composite selections.
        Preferred format (explicit chain mapping):
          - 1XWP A>C,1XWU A>A   (old_chain > new_chain)
        Also accepted (legacy):
          - 1XWP:C,1XWU:A       (keeps old chain; equivalent to A>A)
          - 1XWP,1XWU           (no chain mapping provided)
        Returns list of dicts: { 'pdb_id': '1XWP', 'chain_map': [['A','C']] }
        """
        comps = []
        for raw in re.split(r'[;,]\s*', text.strip()):
            tok = raw.strip()
            if not tok:
                continue
            # Pattern 1: PID <space> A>C  (with optional parentheses)
            m = re.fullmatch(r'([0-9][A-Za-z0-9]{3})\s*(?:\(|)\s*([A-Za-z])\s*>\s*([A-Za-z])\s*(?:\)|)$', tok)
            if m:
                pid = m.group(1).upper()
                old_c = m.group(2).upper()
                new_c = m.group(3).upper()
                comps.append({'pdb_id': pid, 'chain_map': [[old_c, new_c]]})
                continue
            # Pattern 2: PID:Chain (legacy)
            m2 = re.fullmatch(r'([0-9][A-Za-z0-9]{3})\s*[:\(]\s*([A-Za-z])\s*\)?$', tok)
            if m2:
                pid = m2.group(1).upper()
                ch = m2.group(2).upper()
                comps.append({'pdb_id': pid, 'chain_map': [[ch, ch]]})
                continue
            # Pattern 3: Bare PID
            m3 = re.fullmatch(r'([0-9][A-Za-z0-9]{3})$', tok)
            if m3:
                pid = m3.group(1).upper()
                comps.append({'pdb_id': pid})
                continue
        return comps

    processed = 0
    for slug, entry in aptamers.items():
        if args.single and slug != args.single:
            continue
        st = (entry.get('structure') or {})
        viewer = (st.get('viewer') or {})
        pdb_info = (viewer.get('pdb_info') or {})
        pdb_path = pdb_info.get('pdb_file_path')
        if not pdb_path:
            # 没有页面指定的 PDB 文件，则跳过（不再回退到结构汇总里的所有 PDB）
            # 这样可以严格遵循“仅注释页面选用的结构”的约定。
            if args.verbose:
                print(f'[{slug}] skip: no pdb_file_path in viewer.pdb_info')
            continue
        # 支持直接使用本地 mmCIF（若页面引用了 .cif 文件）
        local_cif_abs = None
        try:
            if isinstance(pdb_path, str) and pdb_path.lower().endswith('.cif'):
                candidate = repo_root / pdb_path.lstrip('/')
                if candidate.exists():
                    local_cif_abs = candidate
                    if args.verbose:
                        print(f'[{slug}] found local CIF: {candidate}')
        except Exception:
            pass
        color_schemes = viewer.get('color_schemes') or []
        title = entry.get('title') or ((entry.get('post') or {}).get('meta') or {}).get('title')

        # 仅注释“页面中选用”的 PDB：优先使用 pdb_info.pdb_id，其次从 pdb_file_path 猜测
        primary_pid = None
        pdb_id_from_info = pdb_info.get('pdb_id')
        composite_components = None
        # Overrides may be str (single), list (multiple), or object with 'composite' and optional 'mode'
        if slug in overrides:
            ov = overrides.get(slug)
            ov_mode = None
            if isinstance(ov, str) and is_valid_pdb_id(ov):
                primary_pid = ov.strip().upper()
                if args.verbose:
                    print(f'[{slug}] override -> {primary_pid}')
            elif isinstance(ov, list):
                tmp = []
                for x in ov:
                    if isinstance(x, str) and is_valid_pdb_id(x):
                        tmp.append({'pdb_id': x.strip().upper()})
                if tmp:
                    composite_components = tmp
                    if args.verbose:
                        print(f'[{slug}] override composite(list) -> {[c["pdb_id"] for c in tmp]}')
            elif isinstance(ov, dict) and isinstance(ov.get('composite'), list):
                tmp = []
                for comp in ov.get('composite'):
                    if not isinstance(comp, dict):
                        continue
                    pid = comp.get('pdb_id')
                    if is_valid_pdb_id(pid):
                        item = {'pdb_id': pid.strip().upper()}
                        chs = comp.get('chains')
                        if isinstance(chs, list):
                            item['chains'] = [str(c).upper()[:1] for c in chs if str(c)]
                        cmap = comp.get('chain_map') or comp.get('map')
                        if isinstance(cmap, list) and len(cmap) >= 1:
                            # Expect [[old,new], ...]; we only use first mapping if provided
                            try:
                                first = cmap[0]
                                if isinstance(first, (list, tuple)) and len(first) == 2:
                                    item['chain_map'] = [[str(first[0]).upper()[:1], str(first[1]).upper()[:1]]]
                            except Exception:
                                pass
                        tmp.append(item)
                if tmp:
                    composite_components = tmp
                    if args.verbose:
                        print(f'[{slug}] override composite(object) -> {[c["pdb_id"] for c in tmp]}')
                ov_mode = ov.get('mode') if isinstance(ov.get('mode'), str) else None
            if isinstance(ov_mode, str) and ov_mode in ('merge', 'separate'):
                multi_mode = ov_mode
            else:
                multi_mode = args.multi_mode
        else:
            multi_mode = args.multi_mode
        
        # If composite override present, ignore singular primary selection path
        if composite_components is None and is_valid_pdb_id(pdb_id_from_info):
            primary_pid = pdb_id_from_info.strip().upper()
            if args.verbose:
                print(f'[{slug}] using pdb_info.pdb_id = {primary_pid}')
        else:
            if args.verbose and pdb_id_from_info:
                print(f'[{slug}] ignore invalid pdb_info.pdb_id = {pdb_id_from_info!r}')
            primary_pid = guess_pdb_id_from_path(pdb_path)
            if args.verbose:
                print(f'[{slug}] guessed from path {pdb_path} -> {primary_pid}')

        # 页面可能包含多模型（pdb_blocks），自动识别（例如 Beetroot）
        if composite_components is None:
            page_blocks = viewer.get('pdb_blocks') if isinstance(viewer.get('pdb_blocks'), list) else []
            page_pids: list[str] = []
            for blk in page_blocks:
                if not isinstance(blk, dict):
                    continue
                pth = ((blk.get('pdb_info') or {}) or {}).get('pdb_file_path')
                if isinstance(pth, str):
                    pid = guess_pdb_id_from_path(pth)
                    if pid and is_valid_pdb_id(pid):
                        pid = pid.upper()
                        if pid not in page_pids:
                            page_pids.append(pid)
            if page_pids:
                if len(page_pids) >= 2:
                    composite_components = [{'pdb_id': pid} for pid in page_pids]
                    if args.verbose:
                        print(f'[{slug}] page multi-model detected -> {page_pids}')
                elif primary_pid is None:
                    primary_pid = page_pids[0]
                    if args.verbose:
                        print(f'[{slug}] page single-model -> {primary_pid}')
        if composite_components is None and not primary_pid and local_cif_abs is None:
            # Optional fallback: use the first ID from summary
            all_summary_pids = []
            for pid in ((st.get('summary') or {}).get('pdb_ids') or []):
                if is_valid_pdb_id(pid):
                    all_summary_pids.append(pid.strip().upper())
            if args.fallback_summary and all_summary_pids:
                primary_pid = all_summary_pids[0]
                if args.verbose:
                    print(f'[{slug}] fallback-summary -> {primary_pid} (from {all_summary_pids})')
            elif args.prompt_missing:
                # Interactive prompt
                print('\n=== Missing primary PDB for aptamer ===')
                print(f'- slug   : {slug}')
                print(f'- title  : {title}')
                print(f'- pdb_info: {pdb_info}')
                print(f'- page file path: {pdb_path}')
                post_file = ((entry.get('post') or {}).get('meta') or {}).get('filename')
                if post_file:
                    print(f'- post file: _posts/{post_file}')
                if all_summary_pids:
                    print(f'- candidates from summary: {", ".join(all_summary_pids)}')
                while True:
                    user_in = input("Enter PDB ID or composite list (e.g. '1XWP A>C,1XWU A>A' or legacy '1XWP:C,1XWU:A'), OR index (1..N), OR path to local .cif; 's' to skip, 'q' to quit: ").strip()
                    if not user_in:
                        continue
                    # quit
                    if user_in.lower() in ('q', 'quit', 'exit'):
                        print('Aborted by user.')
                        return
                    # skip
                    if user_in.lower() in ('s', 'skip'):
                        break
                    # multiple IDs -> composite
                    if any(sep in user_in for sep in (',', ';', '+')):
                        comps = parse_composite_input(user_in)
                        if comps:
                            composite_components = comps
                            print(f'- chosen composite -> {[c["pdb_id"] + (":"+c["chains"][0] if c.get("chains") else "") for c in comps]}')
                            break
                        else:
                            print('! Failed to parse composite input')
                            continue
                    # candidate index
                    if user_in.isdigit() and all_summary_pids:
                        idx = int(user_in)
                        if 1 <= idx <= len(all_summary_pids):
                            primary_pid = all_summary_pids[idx - 1]
                            print(f'- chosen summary[{idx}] -> {primary_pid}')
                            break
                        else:
                            print('! Invalid index range')
                            continue
                    # PDB ID
                    if is_valid_pdb_id(user_in):
                        primary_pid = user_in.upper()
                        print(f'- chosen PDB ID -> {primary_pid}')
                        break
                    # local .cif path
                    pth = Path(user_in.strip('"\''))
                    if user_in.lower().endswith('.cif') and (pth.is_absolute() or (repo_root / pth).exists()):
                        local_cif_abs = pth if pth.is_absolute() else (repo_root / pth)
                        if local_cif_abs.exists():
                            print(f'- chosen local CIF -> {local_cif_abs}')
                            break
                        else:
                            print('! CIF path not found')
                            continue
                    print('! Invalid input, try again')
                if composite_components is None and not primary_pid and local_cif_abs is None:
                    # user skipped; record error and continue
                    items_by_slug.setdefault(slug, {'slug': slug, 'title': title})
                    items_by_slug[slug].update({
                        'pdb': pdb_path,
                        'error': 'no_primary_pdb_from_page',
                        'debug': {
                            'pdb_info_has_id': bool(pdb_info.get('pdb_id')),
                            'pdb_info_id': pdb_info.get('pdb_id'),
                            'pdb_file_path': pdb_path
                        }
                    })
                    continue
                # Persist chosen PDB ID if applicable
                if args.save_overrides:
                    if composite_components:
                        overrides[slug] = {'composite': composite_components}
                    elif primary_pid:
                        overrides[slug] = primary_pid
                    try:
                        Path(args.save_overrides).write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding='utf-8')
                        if args.verbose:
                            print(f'- saved override {slug}:{primary_pid} -> {args.save_overrides}')
                    except Exception as e:
                        print(f'! failed to save overrides: {e}')
            else:
                items_by_slug.setdefault(slug, {'slug': slug, 'title': title})
                items_by_slug[slug].update({
                    'pdb': pdb_path,
                    'error': 'no_primary_pdb_from_page',
                    'debug': {
                        'pdb_info_has_id': bool(pdb_info.get('pdb_id')),
                        'pdb_info_id': pdb_info.get('pdb_id'),
                        'pdb_file_path': pdb_path
                    }
                })
                if args.verbose:
                    print(f'[{slug}] ERROR no_primary_pdb_from_page; pdb_info={pdb_info}')
                continue
        if composite_components is None and primary_pid is not None:
            primary_pid = primary_pid.upper()

        # 其他与该 aptamer 相关但“未在页面选用”的结构，作为 related 原始 CIF，一并打包但不写注释
        all_summary_pids = []
        for pid in ((st.get('summary') or {}).get('pdb_ids') or []):
            if is_valid_pdb_id(pid):
                all_summary_pids.append(pid.strip().upper())
        selected_ids = set([primary_pid]) if composite_components is None and primary_pid else set([c['pdb_id'] for c in (composite_components or [])])
        related_pids = [pid for pid in all_summary_pids if pid not in selected_ids]

        # Ensure dir
        out_dir = out_root / slug
        out_dir.mkdir(parents=True, exist_ok=True)

        raw_paths = []
        annotated_paths = []
        component_list_for_index = []
        merged_raw_rel = None
        merged_ann_rel = None

        # Augment prompt: if one primary chosen but more summary IDs available
        if composite_components is None and primary_pid and args.prompt_augment:
            addable = [pid for pid in all_summary_pids if pid != primary_pid]
            if addable:
                print(f"\n=== Additional page PDBs (optional) ===\n- slug: {slug}\n- detected: {primary_pid}\n- candidates: {', '.join(addable)}")
                ans = input("Add more PDB IDs for this page? Enter composite list (e.g. '8EYU A>A,8EYW A>A') or simple '8EYU,8EYW'; Enter to skip: ").strip()
                if ans:
                    comps = parse_composite_input(ans)
                    # include primary as first component
                    tmp = [{'pdb_id': primary_pid}]
                    for c in comps:
                        if is_valid_pdb_id(c.get('pdb_id')) and c.get('pdb_id').upper() != primary_pid:
                            tmp.append({'pdb_id': c['pdb_id'].upper(), 'chains': c.get('chains') or []})
                    if len(tmp) > 1:
                        composite_components = tmp
                        if args.verbose:
                            print(f'[{slug}] augment -> {[c["pdb_id"] for c in tmp]}')

        if composite_components is not None:
            # Composite: process each component separately, annotate, and pack together
            for comp in composite_components:
                pid = comp.get('pdb_id')
                if not is_valid_pdb_id(pid):
                    continue
                pid = pid.upper()
                comp_raw = out_dir / f'{pid}.cif'
                comp_ann = out_dir / f'{pid}.annotated.cif'
                cif_bytes = load_local_cif(repo_root, pid)
                if cif_bytes is None and not args.offline:
                    try:
                        cif_bytes = download_cif(pid, timeout=args.net_timeout, retries=args.net_retries, retry_delay=args.retry_delay)
                    except (URLError, HTTPError, TimeoutError, socket.timeout, OSError):
                        continue
                elif cif_bytes is None and args.offline:
                    continue
                if not comp_raw.exists() or len(comp_raw.read_bytes()) != len(cif_bytes):
                    comp_raw.write_bytes(cif_bytes)
                cif_text = cif_bytes.decode('utf-8', errors='replace')
                annotated_text = annotate_cif(cif_text, slug, title, color_schemes)
                comp_ann.write_text(annotated_text, encoding='utf-8')
                raw_paths.append(str(comp_raw.relative_to(out_root)))
                annotated_paths.append(str(comp_ann.relative_to(out_root)))
                component_list_for_index.append({'pdb_id': pid, 'chain_map': comp.get('chain_map') or [], 'chains': comp.get('chains') or []})
                processed += 1
            # Write composite manifest
            manifest = {
                'slug': slug,
                'title': title,
                'components': component_list_for_index,
                'note': 'Composite structure pack; each CIF annotated separately. Use Mol* multi-load if needed.'
            }
            (out_dir / 'composite.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            primary_id_for_index = ','.join([c['pdb_id'] for c in component_list_for_index]) if component_list_for_index else None

            # Optional merged CIF (experimental multi-block concat)
            merged_raw_rel = None
            merged_ann_rel = None
            # Ask interactively if not specified by overrides
            if multi_mode not in ('merge', 'separate'):
                mode_ans = input("Merge selected structures into a single mmCIF? [y/N]: ").strip().lower()
                multi_mode = 'merge' if mode_ans == 'y' else 'separate'
            if multi_mode == 'merge' and component_list_for_index:
                merged_raw = out_dir / 'merged.cif'
                merged_ann = out_dir / 'merged.annotated.cif'
                engine = args.merge_engine
                if engine == 'auto':
                    try:
                        import shutil as _shutil
                        if _shutil.which('pymol'):
                            engine = 'pymol'
                        else:
                            import gemmi  # noqa: F401
                            engine = 'gemmi'
                    except Exception:
                        engine = 'concat'

                def merge_with_pymol():
                    import tempfile, textwrap, shutil
                    pml_lines = [
                        'reinitialize',
                        'set retain_order, 1',
                    ]
                    for i, comp in enumerate(component_list_for_index, start=1):
                        pid = comp['pdb_id']
                        obj = f'obj{i}'
                        sel = f'sel{i}'
                        pml_lines.append(f'load "{(out_dir / (pid + ".cif")).as_posix()}", {obj}')
                        # Apply chain mapping if provided
                        maps = comp.get('chain_map') or []
                        if maps:
                            oldc, newc = maps[0]
                            pml_lines.append(f'create {sel}, {obj} and chain {oldc}')
                            if oldc != newc:
                                pml_lines.append(f'alter {sel}, chain="{newc}"')
                        else:
                            pml_lines.append(f'create {sel}, {obj}')
                        if i == 1:
                            pml_lines.append('create merged, ' + sel)
                        else:
                            pml_lines.append('create merged, merged or ' + sel)
                    pml_lines.append(f'save "{merged_raw.as_posix()}", merged')
                    pml_lines.append('quit')
                    pml = '\n'.join(pml_lines)
                    tmp_pml = out_dir / 'merge.pml'
                    tmp_pml.write_text(pml, encoding='utf-8')
                    import subprocess
                    subprocess.run(['pymol', '-cq', str(tmp_pml)], check=True)

                def merge_with_gemmi():
                    # Fallback to concatenation if gemmi logic fails
                    try:
                        import gemmi
                        merged = gemmi.Structure()
                        merged.name = slug[:20]
                        mdl = gemmi.Model('1')
                        merged.add_model(mdl)
                        for comp in component_list_for_index:
                            pid = comp['pdb_id']
                            maps = comp.get('chain_map') or []
                            oldc, newc = (maps[0] if maps else (None, None))
                            st = gemmi.read_structure(str(out_dir / f'{pid}.cif'))
                            if not st:
                                continue
                            src_model = st[0]
                            for ch in src_model:
                                use_chain = False
                                new_name = ch.name
                                if oldc:
                                    if ch.name == oldc:
                                        use_chain = True
                                        new_name = newc or oldc
                                else:
                                    use_chain = True
                                if use_chain:
                                    ch_copy = gemmi.Chain(new_name)
                                    for res in ch:
                                        res_copy = gemmi.Residue(res.name, res.seqid)
                                        for atom in res:
                                            atom_copy = gemmi.Atom(atom)
                                            res_copy.add_atom(atom_copy)
                                        ch_copy.add_residue(res_copy)
                                    mdl.add_chain(ch_copy)
                        # Write mmCIF
                        doc = gemmi.cif.Document()
                        block = gemmi.cif.Block('merged')
                        doc.add_block(block)
                        # Let gemmi fill minimal mmCIF for structure
                        mmcif = merged.make_mmcif_document()
                        mmcif.write_file(str(merged_raw))
                    except Exception:
                        return False
                    return True

                def merge_with_concat():
                    blocks = []
                    for comp in component_list_for_index:
                        pid = comp['pdb_id']
                        p = out_dir / f'{pid}.cif'
                        if p.exists():
                            blocks.append(p.read_text(encoding='utf-8', errors='replace'))
                    if blocks:
                        merged_text = ('\n# --- combined block separator ---\n').join(blocks)
                        merged_raw.write_text(merged_text, encoding='utf-8')

                ok = True
                try:
                    if engine == 'pymol':
                        merge_with_pymol()
                    elif engine == 'gemmi':
                        ok = merge_with_gemmi()
                        if not ok:
                            merge_with_concat()
                    else:
                        merge_with_concat()
                except Exception:
                    merge_with_concat()

                if merged_raw.exists():
                    ann_text = annotate_cif(merged_raw.read_text(encoding='utf-8', errors='replace'), slug, title, color_schemes)
                    merged_ann.write_text(ann_text, encoding='utf-8')
                    merged_raw_rel = str(merged_raw.relative_to(out_root))
                    merged_ann_rel = str(merged_ann.relative_to(out_root))
                    raw_paths = [merged_raw_rel] + raw_paths
                    annotated_paths = [merged_ann_rel] + annotated_paths

        elif local_cif_abs is not None:
            # 直接使用本地 mmCIF
            base = local_cif_abs.name
            primary_raw_path = out_dir / base
            primary_annotated_path = out_dir / (Path(base).stem + '.annotated.cif')
            cif_bytes = local_cif_abs.read_bytes()
            if not primary_raw_path.exists() or len(primary_raw_path.read_bytes()) != len(cif_bytes):
                primary_raw_path.write_bytes(cif_bytes)
            cif_text = cif_bytes.decode('utf-8', errors='replace')
            annotated_text = annotate_cif(cif_text, slug, title, color_schemes)
            primary_annotated_path.write_text(annotated_text, encoding='utf-8')
            raw_paths.append(str(primary_raw_path.relative_to(out_root)))
            annotated_paths.append(str(primary_annotated_path.relative_to(out_root)))
            processed += 1
            # For index consistency use filename stem as identifier
            primary_id_for_index = Path(base).stem
        else:
            # 下载/读取并注释“主”PDB（按 PDB ID 下载 mmCIF）
            primary_raw_path = out_dir / f'{primary_pid}.cif'
            primary_annotated_path = out_dir / f'{primary_pid}.annotated.cif'
            cif_bytes = load_local_cif(repo_root, primary_pid)
            if cif_bytes is None and not args.offline:
                try:
                    cif_bytes = download_cif(primary_pid, timeout=args.net_timeout, retries=args.net_retries, retry_delay=args.retry_delay)
                except (URLError, HTTPError, TimeoutError, socket.timeout, OSError) as e:
                    items_by_slug.setdefault(slug, {'slug': slug, 'title': title})
                    items_by_slug[slug].update({'pdb': primary_pid, 'error': f'download_failed: {e}'})
                    # 即使主结构下载失败，related 也没有意义，直接跳过
                    continue
            elif cif_bytes is None and args.offline:
                items_by_slug.setdefault(slug, {'slug': slug, 'title': title})
                items_by_slug[slug].update({'pdb': primary_pid, 'error': 'offline_no_local_cif'})
                continue

            # 写入主 CIF（原始）
            if not primary_raw_path.exists() or len(primary_raw_path.read_bytes()) != len(cif_bytes):
                primary_raw_path.write_bytes(cif_bytes)

            # 写入注释 CIF
            cif_text = cif_bytes.decode('utf-8', errors='replace')
            annotated_text = annotate_cif(cif_text, slug, title, color_schemes)
            primary_annotated_path.write_text(annotated_text, encoding='utf-8')
            raw_paths.append(str(primary_raw_path.relative_to(out_root)))
            annotated_paths.append(str(primary_annotated_path.relative_to(out_root)))
            processed += 1
            primary_id_for_index = primary_pid

        # 处理“相关但未选用”的结构：仅下载为原始 CIF，置于 related/ 目录，不写注释
        related_dir = out_dir / 'related'
        related_dir.mkdir(parents=True, exist_ok=True)
        related_raw_paths = []
        for rpid in related_pids:
            r_raw = related_dir / f'{rpid}.cif'
            r_bytes = load_local_cif(repo_root, rpid)
            if r_bytes is None and not args.offline:
                try:
                    r_bytes = download_cif(rpid, timeout=args.net_timeout, retries=args.net_retries, retry_delay=args.retry_delay)
                except (URLError, HTTPError, TimeoutError, socket.timeout, OSError):
                    continue  # 忽略单个 related 的失败
            elif r_bytes is None and args.offline:
                continue
            if not r_raw.exists() or len(r_raw.read_bytes()) != len(r_bytes):
                r_raw.write_bytes(r_bytes)
            related_raw_paths.append(str(r_raw.relative_to(out_root)))

        # Update index for this slug
        item = items_by_slug.setdefault(slug, {'slug': slug, 'title': title})
        # Build per-aptamer zip with all annotated CIFs and config
        zip_rel_path = None
        if annotated_paths:
            zip_name = f'{slug}.mmcif.zip'
            zip_path = out_dir / zip_name
            with ZipFile(zip_path, 'w', compression=ZIP_DEFLATED) as zf:
                # add annotated cif files
                for rel in annotated_paths:
                    abs_path = out_root / rel
                    if abs_path.exists():
                        zf.write(abs_path, arcname=Path(rel).name)
                # include config.json if exists
                cfg = out_dir / 'config.json'
                if cfg.exists():
                    zf.write(cfg, arcname='config.json')
                # include related raw CIFs under related/
                for rel in related_raw_paths:
                    abs_path = out_root / rel
                    if abs_path.exists():
                        # Ensure files are stored under related/ in the zip
                        arc = Path('related') / Path(rel).name if Path(rel).parent.name == 'related' else Path(rel)
                        zf.write(abs_path, arcname=str(arc))
                # include composite manifest if exists
                comp_manifest = out_dir / 'composite.json'
                if comp_manifest.exists():
                    zf.write(comp_manifest, arcname='composite.json')
                # include merged files if created
                if merged_raw_rel:
                    p = out_root / merged_raw_rel
                    if p.exists():
                        zf.write(p, arcname=Path(merged_raw_rel).name)
                if merged_ann_rel:
                    p = out_root / merged_ann_rel
                    if p.exists():
                        zf.write(p, arcname=Path(merged_ann_rel).name)
            zip_rel_path = str(zip_path.relative_to(out_root))

        # Build index item fields
        pdb_list_field = []
        if composite_components is not None:
            pdb_list_field = [c['pdb_id'] for c in component_list_for_index]
        elif primary_id_for_index:
            pdb_list_field = [primary_id_for_index]
        item.update({
            'pdb_list': pdb_list_field,
            'raw_cif_list': raw_paths,
            'annotated_cif_list': annotated_paths,
            'related_raw_cif_list': related_raw_paths,
            **({'composite': True, 'components': component_list_for_index} if composite_components is not None else {}),
            'color_schemes_count': len(color_schemes),
            **({'zip': zip_rel_path} if zip_rel_path else {})
        })

    # Rewrite index
    items = list(items_by_slug.values())
    items.sort(key=lambda x: x.get('slug', ''))
    index = {
        'generated_at': datetime.now().isoformat(),
        'source': args.merged,
        'total': len(items),
        'items': items
    }
    write_json(index_path, index)
    # Stats: items with multiple annotated CIFs / composite
    multi = [it.get('slug') for it in items if len((it.get('annotated_cif_list') or [])) > 1 or it.get('composite')]
    if multi:
        print(f'Multi-annotated or composite aptamers ({len(multi)}): {", ".join(multi[:10])}'+ (' ...' if len(multi)>10 else ''))
    print(f'Annotated mmCIF exported for {processed} aptamers. Index: {index_path}')


if __name__ == '__main__':
    main()
