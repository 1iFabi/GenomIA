import gsap from 'gsap';
import { prefersStill } from './utils';

/**
 * Login and Register are the same two plates in mirrored halves. Moving between them is a sweep:
 *
 *   1. The route changes on the press. The page that leaves plays no animation, so it is never on
 *      screen while the next one loads.
 *   2. The arriving page places its form in its own half at once. The art plate moves: it starts on
 *      the half the other page gave it and sweeps across to its own, uncovering the text as it
 *      leaves, and the text condenses out of a haze behind it.
 *
 * Nothing of the destination is read from the page that left, and the only state the two share is
 * "you are arriving", which the module owns.
 */
const HANDOFF_TTL_MS = 1600;
const SLIDE_S = 0.5;            // the art plate sweeps into its own half
const ENTRANCE_DURATION_S = 0.45;
const STILL_S = 0.16;
const CONTENT_STAGGER_S = 0.04;
const ENTRANCE_SHIFT_PX = 14;
const ENTRANCE_BLUR_PX = 10;    // the text condenses out of a haze, not a flat fade
const ENTRANCE_SCALE = 0.985;
const HAZE_DELAY_S = 0.15;       // on the swap, the text starts to condense as the art clears it
const SLIDE_EASE = 'power3.out';
const CONTENT_EASE = 'expo.out';
// The surface each destination rests on. The page that leaves adopts it on the press, while its
// own plates still cover the viewport, so the handoff cannot step the page tone.
const SURFACE_BY_PATH = { '/register': '#f8fafc', '/login': '#ffffff' };
const SWAP_ROOT_CLASS = 'auth--swapping';
const FORM_PLATE_SELECTOR = '.auth-left';
const ART_PLATE_SELECTOR = '.auth-right';
// Everything the two pages replace, and nothing that carries continuity across them.
const REFRESHING_CONTENT_SELECTOR = '.left-inner > :not(.logo-container)';
// Opacity, never visibility: content stays hit-testable while it fades.
const CLEARED_CONTENT_PROPS = 'opacity,transform,filter';

let handoff = null;
let handoffId = 0;

const normalizePath = (pathname) => (pathname || '/').replace(/\/+$/, '') || '/';

export const armAuthPanelSwap = ({ pathname, keyboard = false }) => {
  handoffId += 1;
  handoff = {
    id: handoffId,
    pathname: normalizePath(pathname),
    keyboard,
    at: Date.now(),
  };
  return handoff;
};

/**
 * Read-only and idempotent: React may render a page twice before committing in development, and a
 * replayed read must see the same handoff.
 */
export const readAuthPanelSwap = (pathname) => {
  if (!handoff || handoff.pathname !== normalizePath(pathname)) return null;
  if (Date.now() - handoff.at > HANDOFF_TTL_MS) return null;
  return handoff;
};

export const resetAuthPanelSwap = () => {
  handoff = null;
  handoffId = 0;
};

/**
 * The art only crosses when both plates are on screen at half width: it has to fit in the half the
 * other page left. A single plate (narrow viewports) lands in place instead.
 */
export const resolveAuthPlateMotion = ({ formWidth, artVisible, viewportWidth }) => (
  artVisible && formWidth <= (viewportWidth / 2) * 1.02 ? 'exchange' : 'in-place'
);

const measurePlates = (root) => {
  const form = root?.querySelector(FORM_PLATE_SELECTOR);
  if (!form) return null;

  const formBox = form.getBoundingClientRect();
  const art = root.querySelector(ART_PLATE_SELECTOR);
  const artBox = art ? art.getBoundingClientRect() : null;

  return {
    form,
    art,
    artVisible: Boolean(artBox && artBox.width > 0 && artBox.height > 0),
    formLeft: formBox.left,
    formWidth: formBox.width,
  };
};

const refreshingContent = (root) => root.querySelectorAll(REFRESHING_CONTENT_SELECTOR);

const clearContentStyles = (root) => {
  const content = refreshingContent(root);
  if (content.length) gsap.set(content, { clearProps: CLEARED_CONTENT_PROPS });
};

/**
 * The text condenses out of a haze: blur, scale and rise resolve together. The from-state is set
 * when the tween is built, so the text is already hazed before the first paint.
 */
const hazeIn = (timeline, content, at = 0) => timeline.fromTo(content, {
  opacity: 0,
  y: ENTRANCE_SHIFT_PX,
  scale: ENTRANCE_SCALE,
  filter: `blur(${ENTRANCE_BLUR_PX}px)`,
}, {
  opacity: 1,
  y: 0,
  scale: 1,
  filter: 'blur(0px)',
  duration: ENTRANCE_DURATION_S,
  stagger: CONTENT_STAGGER_S,
  ease: CONTENT_EASE,
}, at);

/** The leaving page wears the destination's surface; the arrival already has it. */
const adoptDestinationSurface = (root, targetPath) => {
  if (!root) return;
  const surface = SURFACE_BY_PATH[normalizePath(targetPath)] ?? SURFACE_BY_PATH['/login'];
  root.style.backgroundColor = surface;
  const form = root.querySelector(FORM_PLATE_SELECTOR);
  if (form) form.style.backgroundColor = surface;
};

/**
 * Enter the other auth page. Nothing is animated here: the route changes on the press, so the page
 * that leaves is never on screen while the next one loads, and the arriving page plays the move.
 * The destination is imported statically, which is what keeps this instant: a lazy route would
 * suspend into the fallback and show a loader instead.
 */
export const openAuthPanel = ({ root, targetPath, keyboard = false, navigate }) => {
  adoptDestinationSurface(root, targetPath);
  armAuthPanelSwap({ pathname: targetPath, keyboard });
  navigate(targetPath);
};

/**
 * The arrival plays the sweep. The art starts on the half the other page left and crosses into its
 * own, while the form is already in place and its text condenses in behind the art. A single plate
 * lands in place with the same haze; a reduced-motion preference does nothing.
 */
export const playAuthPlateEntry = (root, { reducedMotion = prefersStill(), focusTarget = null } = {}) => {
  const done = () => {
    if (focusTarget) focusTarget.focus({ preventScroll: true });
  };

  const plates = measurePlates(root);
  if (!plates || reducedMotion) {
    done();
    return gsap.timeline();
  }

  const mode = resolveAuthPlateMotion({
    formWidth: plates.formWidth,
    artVisible: plates.artVisible,
    // clientWidth, not innerWidth: a classic scrollbar takes its width out of the layout.
    viewportWidth: document.documentElement.clientWidth,
  });

  const content = refreshingContent(root);
  const settle = () => clearContentStyles(root);

  if (mode === 'in-place') {
    done();
    return hazeIn(gsap.timeline({ onComplete: settle }), content);
  }

  // A form on the left means the art sits on the right, so it starts on the left, where the other
  // page had it. A form on the right is the mirror image.
  const formOnTheLeft = plates.formLeft + plates.formWidth / 2 <= document.documentElement.clientWidth / 2;
  const artStart = formOnTheLeft ? -plates.formWidth : plates.formWidth;

  root.classList.add(SWAP_ROOT_CLASS);
  gsap.set(plates.art, { x: artStart });

  const slide = gsap.timeline({
    onComplete: () => {
      root.classList.remove(SWAP_ROOT_CLASS);
      gsap.set(plates.art, { clearProps: 'transform' });
      done();
    },
  }).to(plates.art, { x: 0, duration: SLIDE_S, ease: SLIDE_EASE });

  // The art clears the text as it crosses, so the haze starts once the text is uncovering.
  const timeline = gsap.timeline({ onComplete: settle }).add(slide);
  return hazeIn(timeline, content, HAZE_DELAY_S);
};

/** First paint on either page, with no exchange behind it. */
export const playAuthPageEntrance = (root, { reducedMotion = prefersStill() } = {}) => {
  const content = refreshingContent(root);
  if (!content.length) return gsap.timeline();

  const settle = () => clearContentStyles(root);

  if (reducedMotion) {
    gsap.set(content, { opacity: 0 });
    return gsap.timeline({ onComplete: settle })
      .to(content, { opacity: 1, duration: STILL_S, ease: 'power1.out' });
  }

  return hazeIn(gsap.timeline({ onComplete: settle }), content);
};
