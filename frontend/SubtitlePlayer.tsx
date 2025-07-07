// SubtitlePlayer.tsx - Караоке субтитры для AgentFlow AI Clips
// Компонент для отображения субтитров с подсветкой слов в стиле Opus.pro

import React, { useState, useEffect, useRef } from 'react';
import './SubtitlePlayer.css';

interface Word {
  word: string;
  start: number;
  end: number;
  score?: number;
}

interface Segment {
  id: number;
  start: number;
  end: number;
  text: string;
  words: Word[];
}

interface SubtitleData {
  text: string;
  segments: Segment[];
}

interface SubtitlePlayerProps {
  videoRef: React.RefObject<HTMLVideoElement>;
  subtitleData: SubtitleData | null;
  style?: 'modern' | 'classic' | 'neon' | 'minimal';
  position?: 'bottom' | 'top' | 'center';
  fontSize?: 'small' | 'medium' | 'large';
  showBackground?: boolean;
  highlightColor?: string;
  textColor?: string;
}

export const SubtitlePlayer: React.FC<SubtitlePlayerProps> = ({
  videoRef,
  subtitleData,
  style = 'modern',
  position = 'bottom',
  fontSize = 'medium',
  showBackground = true,
  highlightColor = '#FFD700',
  textColor = '#FFFFFF'
}) => {
  const [currentTime, setCurrentTime] = useState(0);
  const [currentSegment, setCurrentSegment] = useState<Segment | null>(null);
  const [highlightedWords, setHighlightedWords] = useState<Set<number>>(new Set());
  const subtitleRef = useRef<HTMLDivElement>(null);

  // Обновление текущего времени видео
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleTimeUpdate = () => {
      setCurrentTime(video.currentTime);
    };

    video.addEventListener('timeupdate', handleTimeUpdate);
    return () => video.removeEventListener('timeupdate', handleTimeUpdate);
  }, [videoRef]);

  // Поиск текущего сегмента и подсвеченных слов
  useEffect(() => {
    if (!subtitleData || !subtitleData.segments) return;

    // Находим текущий сегмент
    const segment = subtitleData.segments.find(
      seg => currentTime >= seg.start && currentTime <= seg.end
    );

    setCurrentSegment(segment || null);

    // Находим подсвеченные слова
    if (segment && segment.words) {
      const highlighted = new Set<number>();
      segment.words.forEach((word, index) => {
        if (currentTime >= word.start && currentTime <= word.end) {
          highlighted.add(index);
        }
      });
      setHighlightedWords(highlighted);
    } else {
      setHighlightedWords(new Set());
    }
  }, [currentTime, subtitleData]);

  // Автоскролл к текущему сегменту
  useEffect(() => {
    if (subtitleRef.current && currentSegment) {
      const element = subtitleRef.current.querySelector(`[data-segment-id="${currentSegment.id}"]`);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [currentSegment]);

  if (!subtitleData || !currentSegment) {
    return null;
  }

  const renderWords = (words: Word[]) => {
    return words.map((word, index) => {
      const isHighlighted = highlightedWords.has(index);
      const isActive = currentTime >= word.start && currentTime <= word.end;
      
      return (
        <span
          key={index}
          className={`subtitle-word ${isHighlighted ? 'highlighted' : ''} ${isActive ? 'active' : ''}`}
          style={{
            color: isHighlighted ? highlightColor : textColor,
            transition: 'all 0.2s ease-in-out'
          }}
          data-start={word.start}
          data-end={word.end}
        >
          {word.word}
        </span>
      );
    });
  };

  const containerClasses = [
    'subtitle-player',
    `subtitle-${style}`,
    `subtitle-${position}`,
    `subtitle-${fontSize}`,
    showBackground ? 'with-background' : 'no-background'
  ].join(' ');

  return (
    <div className={containerClasses} ref={subtitleRef}>
      <div className="subtitle-container">
        <div 
          className="subtitle-segment active-segment"
          data-segment-id={currentSegment.id}
          style={{ color: textColor }}
        >
          {currentSegment.words && currentSegment.words.length > 0 
            ? renderWords(currentSegment.words)
            : <span className="subtitle-text">{currentSegment.text}</span>
          }
        </div>
      </div>
      
      {/* Прогресс бар для текущего сегмента */}
      <div className="subtitle-progress">
        <div 
          className="subtitle-progress-bar"
          style={{
            width: `${((currentTime - currentSegment.start) / (currentSegment.end - currentSegment.start)) * 100}%`,
            backgroundColor: highlightColor
          }}
        />
      </div>
    </div>
  );
};

// Хук для управления субтитрами
export const useSubtitlePlayer = (videoRef: React.RefObject<HTMLVideoElement>) => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);
    const handleTimeUpdate = () => setCurrentTime(video.currentTime);
    const handleLoadedMetadata = () => setDuration(video.duration);

    video.addEventListener('play', handlePlay);
    video.addEventListener('pause', handlePause);
    video.addEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('loadedmetadata', handleLoadedMetadata);

    return () => {
      video.removeEventListener('play', handlePlay);
      video.removeEventListener('pause', handlePause);
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('loadedmetadata', handleLoadedMetadata);
    };
  }, [videoRef]);

  const seekTo = (time: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time;
    }
  };

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
    }
  };

  return {
    isPlaying,
    currentTime,
    duration,
    seekTo,
    togglePlay
  };
};

export default SubtitlePlayer;

