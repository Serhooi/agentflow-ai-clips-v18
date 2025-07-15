import React from 'react';
import { Composition, Video, Sequence, AbsoluteFill } from 'remotion';
import { useCurrentFrame, useVideoConfig, interpolate } from 'remotion';

// Компонент для отображения одного слова с анимацией
const AnimatedWord = ({ word, index, currentFrame, fps, isActive }) => {
  const startFrame = Math.floor(word.start * fps);
  const endFrame = Math.floor(word.end * fps);
  
  // Анимация появления/исчезновения
  const opacity = interpolate(
    currentFrame,
    [startFrame - 5, startFrame, endFrame, endFrame + 5],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  );
  
  // Анимация масштаба для активного слова
  const scale = isActive ? interpolate(
    currentFrame,
    [startFrame, startFrame + 3, endFrame - 3, endFrame],
    [1, 1.1, 1.1, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }
  ) : 1;
  
  // Цвет: золотой для активного слова, белый для остальных
  const color = isActive ? '#FFD700' : '#FFFFFF';
  
  return (
    <span
      style={{
        opacity,
        transform: `scale(${scale})`,
        color,
        fontSize: '48px',
        fontFamily: 'Montserrat, Arial, sans-serif',
        fontWeight: 'bold',
        margin: '0 8px',
        textShadow: isActive 
          ? '0 0 20px rgba(255, 215, 0, 0.8), 2px 2px 4px rgba(0, 0, 0, 0.8)' 
          : '2px 2px 4px rgba(0, 0, 0, 0.8)',
        transition: 'all 0.2s ease',
        display: 'inline-block',
      }}
    >
      {word.word}
    </span>
  );
};

// Компонент субтитров с караоке-эффектом
const SubtitleAnimation = ({ words }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  
  // Группируем слова по 3-5 штук для отображения
  const groupWords = (words, maxWordsPerGroup = 4) => {
    const groups = [];
    let currentGroup = [];
    
    for (const word of words) {
      currentGroup.push(word);
      
      if (currentGroup.length >= maxWordsPerGroup) {
        groups.push([...currentGroup]);
        currentGroup = [];
      }
    }
    
    if (currentGroup.length > 0) {
      groups.push(currentGroup);
    }
    
    return groups;
  };
  
  const wordGroups = groupWords(words);
  
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'flex-end',
        alignItems: 'center',
        padding: '0 40px 120px 40px',
        backgroundColor: 'transparent',
        textAlign: 'center',
      }}
    >
      {wordGroups.map((group, groupIndex) => {
        // Определяем время показа группы
        const groupStartTime = Math.min(...group.map(w => w.start));
        const groupEndTime = Math.max(...group.map(w => w.end));
        const groupStartFrame = Math.floor(groupStartTime * fps);
        const groupEndFrame = Math.floor(groupEndTime * fps);
        
        // Показываем группу только в нужное время
        if (frame < groupStartFrame || frame > groupEndFrame) {
          return null;
        }
        
        return (
          <div
            key={groupIndex}
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'center',
              alignItems: 'center',
              marginBottom: '20px',
              maxWidth: '100%',
            }}
          >
            {group.map((word, wordIndex) => {
              const wordStartFrame = Math.floor(word.start * fps);
              const wordEndFrame = Math.floor(word.end * fps);
              const isActive = frame >= wordStartFrame && frame < wordEndFrame;
              
              return (
                <AnimatedWord
                  key={`${groupIndex}-${wordIndex}`}
                  word={word}
                  index={wordIndex}
                  currentFrame={frame}
                  fps={fps}
                  isActive={isActive}
                />
              );
            })}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

// Основной компонент видео
const VideoComponent = ({ videoPath, words, duration }) => {
  const { fps } = useVideoConfig();
  const durationInFrames = Math.floor(duration * fps);
  
  return (
    <AbsoluteFill>
      {/* Фоновое видео */}
      <Video
        src={videoPath}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
        }}
      />
      
      {/* Субтитры поверх видео */}
      <SubtitleAnimation words={words} />
    </AbsoluteFill>
  );
};

// Экспорт композиции
export const MyVideo = () => {
  return (
    <Composition
      id="MyVideo"
      component={VideoComponent}
      durationInFrames={900} // 30 секунд при 30 FPS (будет переопределено через props)
      fps={30}
      width={720}
      height={1280}
    />
  );
};

// Регистрация композиций (обязательно для Remotion)
export default function Root() {
  return (
    <>
      <Composition
        id="MyVideo"
        component={VideoComponent}
        durationInFrames={900}
        fps={30}
        width={720}
        height={1280}
        defaultProps={{
          videoPath: '',
          words: [],
          duration: 30
        }}
      />
    </>
  );
}

