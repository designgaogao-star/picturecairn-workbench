import mark from '../../../docs/brand/stillmark/extra/stillmark-mark-24.svg?raw';
import wordmark from '../../../docs/brand/stillmark/extra/stillmark-wordmark-ui.svg?raw';
import stacked from '../../../docs/brand/stillmark/extra/stillmark-lockup-stacked.svg?raw';
import white from '../../../docs/brand/stillmark/extra/stillmark-tray-white.svg?raw';

export const PRODUCT_NAME = 'Stillmark 影迹图片工作台';

/** These are trusted, validated, repository-owned SVG sources, never server or user content. */
export function Brand() {
  return <span class="brand" role="img" aria-label={PRODUCT_NAME}>
    <span class="brand-mark" aria-hidden="true" dangerouslySetInnerHTML={{ __html: mark }} />
    <span class="brand-type" aria-hidden="true">
      <span class="brand-wordmark" dangerouslySetInnerHTML={{ __html: wordmark }} />
      <span class="brand-subtitle">影迹图片工作台</span>
    </span>
  </span>;
}

export function BrandSplash() {
  return <span class="brand-splash" role="img" aria-label={PRODUCT_NAME} dangerouslySetInnerHTML={{ __html: stacked }} />;
}

export function ViewerBrand() {
  return <span class="viewer-brand" aria-hidden="true" dangerouslySetInnerHTML={{ __html: white }} />;
}
