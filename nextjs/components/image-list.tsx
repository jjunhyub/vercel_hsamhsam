// @ts-nocheck
'use client';

import { useMemo, useState } from 'react';
import { imageComplete, reviewProgress } from '../lib/review-logic';

export default function ImageList({
  records,
  annotations,
  selectedImageId,
  onSelectImage,
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
        <div className="sidebarSectionHeader">Images</div>
        <button
          type="button"
          className="sidebarToggleButton"
          onClick={() => setSortMode((prev) => (prev === 'grouped' ? 'default' : 'grouped'))}
        >
          {sortMode === 'grouped' ? '우선순위 순' : '기본 순서'}
        </button>
      </div>
      <div className="sidebarCount">
        진행률 {completedImageCount}/{imageIds.length} ({overallProgress.toFixed(1)}%)
        {sortMode === 'grouped' ? ' · 진행중 > 미완료 > 완료' : ''}
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
              <div className="imageListItemMeta">진행률: {done}/{total}</div>
              <div className="imageListItemMeta">{progress.toFixed(1)}% 완료</div>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
