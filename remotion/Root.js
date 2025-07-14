import { Composition, Video, Sequence, AbsoluteFill } from 'remotion';
import { useCurrentFrame, useVideoConfig, interpolate } from 'remotion';

// Компонент анимации субтитров
const SubtitleAnimation = ({ words, clipDuration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ justifyContent: 'center', alignItems: 'center', backgroundColor: 'transparent' }}>
      {words.map((word, index) => {
        const startFrame = Math.floor(word.start * fps);
        const endFrame = Math.floor(word.end * fps);
        const opacity = interpolate(frame, [startFrame, startFrame + 5, endFrame - 5, endFrame], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        const scale = interpolate(frame, [startFrame, startFrame + 5, endFrame - 5, endFrame], [0.8, 1, 1, 0.8], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        const color = frame >= startFrame && frame < endFrame ? '#ffd700' : '#fff';

        return (
          <span
            key={index}
            style={{
              opacity,
              transform: `scale(${scale})`,
              color,
              fontSize: '40px',
              fontFamily: 'Arial',
              margin: '0 5px',
              textShadow: frame >= startFrame && frame < endFrame ? '0 0 10px #ffd700' : 'none',
              transition: 'all 0.2s ease',
            }}
          >
            {word.word}
          </span>
        );
      })}
    </AbsoluteFill>
  );
};

// Основной компонент видео
const VideoComponent = ({ videoPath, words, duration }) => {
  return (
    <Sequence>
      <Video src={videoPath} />
      <SubtitleAnimation words={words} clipDuration={duration} />
    </Sequence>
  );
};

// Композиция для рендера
export const MyVideo = ({ videoPath, words, duration, width, height }) => (
  <Composition
    id="MyVideo"
    component={VideoComponent}
    durationInFrames={Math.floor(duration * 30)} // 30 FPS
    fps={30}
    width={width}
    height={height}
    defaultProps={{ videoPath, words, duration }}
  />
);
