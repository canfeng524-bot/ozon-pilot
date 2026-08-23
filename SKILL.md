---
name: ozon-pilot
description: Turn a 1688 or Taobao product link, or an extracted supplier-product folder, into a reviewable Ozon listing package with screened source images, Russian copy, carousel assets, pricing, and export files. Use for building or revising Ozon-ready materials from Chinese supplier data; do not use to publish directly to Ozon.
---

# Ozon Pilot

Use the pipeline in this skill directory to prepare an Ozon listing package from supplier evidence. Resolve commands and relative files from the directory containing this `SKILL.md`; do not assume a particular drive letter or user path. The pipeline stops before Ozon publication; the seller reviews the package and uploads it in the Ozon seller cabinet.

## Choose the intake route

- **Link route:** use a 1688 product URL when a quick image-first draft is sufficient. The public fetcher can retrieve imagery but may not retrieve reliable title, price, attributes, SKU, or logistics fields.
- **Extracted-folder route:** use a folder containing an `info*.json` exported by `userscripts/ozon-intake-extractor.user.js`. Prefer this route for an upload-ready package because it can include title, attributes, SKU options, and packaged weight/dimensions.
- **Saved-page route:** when the source page cannot be read, ask for the saved `.htm`, screenshots, or a supplier export. Do not bypass CAPTCHA or request login credentials/cookies.

Read `config.yaml` before execution. It controls the workspace location, carousel plan, model integrations, image dimensions, price assumptions, and Russian copy prompt.

## Run the pipeline

From the directory containing this `SKILL.md`:

```powershell
python run.py "<1688 URL>"
python run.py "<extracted product folder>"
python run.py "<input>" --skip-ai
```

Use `--skip-ai` when the user wants only real source material and deterministic program layouts. With model credentials absent, the pipeline deliberately degrades to a screening heuristic, a `copy_prompt.md`, and `remastered/ai_todo.json`; explain these manual hand-off points instead of claiming AI assets or copy were generated.

Do not overwrite an existing `listing.json` or a completed remastered asset unless the user asks to regenerate it. Inspect the existing product folder first and tell the user which artifacts would be reused.

## Evidence and claims

Treat product facts as evidence-bound:

- Link-mode price and availability are temporary sourcing observations, not Ozon listing claims.
- Do not make a material, dimension, capacity, compatibility, certification, warranty, safety, waterproofing, origin, or package-content claim unless it appears in the supplier extract, supplier detail image, or user-provided documentation.
- If source text, images, SKU fields, and logistics values conflict, flag the conflict for review. Do not silently select the most attractive value.
- Never infer A4/laptop fit from a generic size diagram. Do not generate a size card when key dimensions are absent; request confirmation instead.
- Do not use competitor brands, luxury-model names, seller names, or copied competitor text in Russian copy.

Before the user uploads anything, remind them to confirm the exact SKU, source-photo commercial-use rights, product sample, category-specific Ozon attributes, and any documentation required for the declared material.

## Russian listing language

Build titles in the order `core search phrase → verified differentiating attributes → relevant long-tail use phrase`. Put a natural Russian category phrase first because search cards truncate the title. Choose wording Russians actually use on marketplaces rather than translating the Chinese supplier title word-for-word. Title attributes should normally be material, colour, model, or a core function; keep exact dimensions in the attribute table, description, and size card unless the category or user explicitly requires them in the title. Use only product-relevant synonyms and scenarios: search coverage is not permission to add gift, home, work, school, date, or travel terms indiscriminately. For a supported women's crossbody bag, phrases such as `сумка женская через плечо`, `кросс-боди`, and `повседневная` may be natural; select the smallest non-repetitive set that accurately describes the item. Put additional plausible occasions in the description rather than stuffing the title.

Current Ozon wording, seasonality, and nearby Russian holidays may inform a scene phrase, but use a dynamic term only when it is both product-relevant and supported by a dated current-site check. Record the check date and source in the work notes. Without Ozon Seller query-frequency or conversion data, describe the evidence as current on-site wording rather than claiming a quantitatively high-volume or high-quality keyword. Use at most one seasonal or holiday phrase in a title, remove it when stale, and never force a holiday term into an unrelated product.

Apply the same standard to highlights, descriptions, attributes, and image captions. Russian copy must read as native marketplace language, preserve evidence-bound facts, and avoid Chinese syntax carried into Russian.

## Images and creative

Keep the first image product-led and use real product evidence for dimensions, material, hardware, interior, color, and accessories. Do not allow an AI-rendered product to replace the evidence images when silhouette, texture, color, or hardware differs from the source.

For bags and similar fashion accessories, use one actual-use primary image plus one primary-image alternative when requested; Ozon uses only the first as the listing cover. Include two distinct active-use lifestyle secondary images when requested or when the carousel plan calls for them. The primary-image model must not show their face. Use an original fictional adult model—not a supplier model, celebrity, influencer, or competitor model—with no recognizable campaign or branding. Within one product carousel, use the same fictional model in every lifestyle scene unless the user explicitly requests otherwise: make the first approved image the identity anchor and preserve facial structure, age, body build, hair, and skin tone in later images while changing only scene, clothing, pose, and use action.

Use different buyer contexts, such as weekday commute and weekend shopping/café; the product must be visibly used and its key details remain readable. Treat these images as atmosphere/use-context, not proof of material microtexture. Side/back angles, interior organization, capacity demonstrations, material/hardware macro shots, adjustable or detachable straps, and colour collections require matching source evidence; leave the slot empty when it is absent. Keep Russian text overlays in deterministic program layouts, not in generated imagery. Create a colour collection only for confirmed multiple SKUs with a real image for every colour.

Final Ozon carousel images must not contain supplier-page Chinese headings, captions, badges, watermarks, or other non-Russian source text. Treat any such text in `remastered/` as a failed QA result even when a Russian caption was added elsewhere. Crop the source to a clean product-only region with an explicit `slots.json` crop, rebuild the scene from evidence, or leave the slot empty. Never cover Chinese text with a patch that hides product pixels or creates a misleading edit. Inspect every final carousel image at readable size before packaging.

For bag capacity cards, prefer a clean white or minimal tabletop and show only source-backed internal structures. Everyday objects such as a phone, compact wallet, or keys may illustrate scale when dimensions support them, but do not invent dividers, zipped pockets, or organizers. For size cards, label `Ширина`, `Высота`, and `Глубина` in Russian and use an ordinary smartphone of about 7.5×15 cm as the consistent same-scale reference. Do not mix A4 sheets, tablets, laptops, or changing reference objects across products unless the user explicitly asks and the comparison is evidence-safe.

Use the Russian listing title—not the supplier's Chinese title—as the review-page title once `listing.json` exists. The review image matrix must follow `carousel_plan` order. In the export ZIP and Excel image list, prefix existing images with consecutive two-digit sequence numbers in that same order, such as `01_main.jpg`, `02_main_alt.jpg`, and `03_model1.jpg`; do not rely on alphabetical filesystem order.

## Review and handoff

Inspect the package before calling it ready:

- `screen.json` — selections, tags, and rejected source images;
- `remastered/` — carousel images and any unresolved `ai_todo.json`;
- `listing.json` or `copy_prompt.md` — Russian listing content;
- `review.html` — visual QA page;
- `ozon_listing.xlsx` and `ozon_package.zip` — generated only when their prerequisites are present.

Report missing slots, unsupported claims, model/API fallbacks, and any image/product mismatch. Never claim that a package has been uploaded or approved by Ozon unless the user separately authorizes and completes that action.

## Maintenance

When changing this skill's operational behavior, update the matching pipeline code and `config.yaml` together, then validate by running the relevant script or a safe dry invocation. Keep `README.md` aligned with externally visible command behavior.
