// @ts-nocheck
'use client';

import { useMemo, useState } from 'react';
import { imageComplete, reviewProgress } from '../lib/review-logic';
import { uiText } from '../lib/i18n';

export default function ImageList({
  records,
  annotations,
  selectedImageId,
  onSelectImage,
  language,
}) {
  const [sortMode, setSortMode] = useState('grouped');
  const imageIds = Object.keys(records || {});
  const completedImageCount = useMemo(
    () => imageIds.filter((imageId) => imageComplete(annotations, imageId, records[imageId])).length,
    [annotations, imageIds, records]
  );
  const overallProgress = imageIds.length ? (completedImageCount / imageIds.length) * 100 : 0;
  const filteredItems = useMemo(() => {
    const items = imageIds
      .map((imageId, index) => {
        const record = records[imageId];
        const [done, total] = reviewProgress(annotations, imageId, record);
        const completed = imageComplete(annotations, imageId, record);
        const progress = total > 0 ? (done / total) * 100 : 0;
        const group = completed ? 2 : done > 0 ? 0 : 1;

        return {
          imageId,
          index,
          done,
          total,
          completed,
          progress,
          group,
        };
      });

    if (sortMode === 'default') {
      return items;
    }

    return [...items].sort((a, b) => {
      if (a.group !== b.group) return a.group - b.group;
      return a.index - b.index;
    });
  }, [annotations, imageIds, records, sortMode]);

  return (
    <aside className="leftSidebar">
      <div className="sidebarHeaderRow">
        <div className="sidebarSectionHeader">{uiText(language, 'imageList.title')}</div>
        <button
          type="button"
          className="sidebarToggleButton"
          onClick={() => setSortMode((prev) => (prev === 'grouped' ? 'default' : 'grouped'))}
        >
          {sortMode === 'grouped' ? uiText(language, 'imageList.recommendedOrder') : uiText(language, 'imageList.defaultOrder')}
        </button>
      </div>
      <div className="sidebarCount">
        {uiText(language, 'imageList.overallProgress', {
          completed: completedImageCount,
          total: imageIds.length,
          percent: overallProgress.toFixed(1),
        })}
      </div>

      <div className="imageListScroller">
        {filteredItems.map((item) => {
          const { imageId, done, total, completed, progress } = item;
          const selected = selectedImageId === imageId;
          const displayId = /^\d+$/.test(String(imageId)) ? String(Number(imageId)) : String(imageId);
          const icon = completed ? '🟦' : done > 0 ? '🟡' : '⬜';

          return (
            <button
              key={imageId}
              type="button"
              className={[
                'imageListItem',
                selected ? 'isSelected' : '',
                completed ? 'isDone' : '',
              ].join(' ')}
              onClick={() => onSelectImage(imageId)}
            >
              <div className="imageListItemTitle">{icon} {displayId}</div>
              <div className="imageListItemMeta">{uiText(language, 'imageList.progress', { done, total })}</div>
              <div className="imageListItemMeta">{uiText(language, 'imageList.complete', { percent: progress.toFixed(1) })}</div>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
