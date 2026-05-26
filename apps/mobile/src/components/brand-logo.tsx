import { Platform, StyleSheet, Text, View, type ViewStyle } from 'react-native';

type Size = 'sm' | 'md' | 'lg';

const SIZES: Record<Size, { bug: number; bugFont: number; word: number; gap: number }> = {
  sm: { bug: 28, bugFont: 14, word: 18, gap: 8 },
  md: { bug: 40, bugFont: 20, word: 24, gap: 10 },
  lg: { bug: 56, bugFont: 28, word: 32, gap: 14 },
};

// ClaroBill brand mark: sage rounded-square "C" bug + serif wordmark.
// Pure View/Text — no image asset needed. Scales cleanly via the `size` prop.
export function BrandLogo({
  size = 'md',
  containerStyle,
}: {
  size?: Size;
  containerStyle?: ViewStyle;
}) {
  const s = SIZES[size];

  return (
    <View
      style={[styles.row, containerStyle]}
      accessibilityRole="image"
      accessibilityLabel="ClaroBill"
    >
      <View
        style={[
          styles.bug,
          {
            width: s.bug,
            height: s.bug,
            borderRadius: s.bug * 0.25,
          },
        ]}
      >
        <Text
          style={[
            styles.bugLetter,
            { fontSize: s.bugFont, lineHeight: s.bug },
          ]}
        >
          C
        </Text>
      </View>
      <View style={{ width: s.gap }} />
      <Text style={[styles.word, { fontSize: s.word }]}>
        Claro<Text style={styles.wordItalic}>Bill</Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center' },
  bug: {
    backgroundColor: '#2D4A2A',
    justifyContent: 'center',
    alignItems: 'center',
  },
  bugLetter: {
    color: '#C8F060',
    fontFamily: Platform.select({ ios: 'Georgia', android: 'serif' }),
    fontStyle: 'italic',
    fontWeight: '700',
    textAlign: 'center',
    includeFontPadding: false,
  },
  word: {
    fontFamily: Platform.select({ ios: 'Georgia', android: 'serif' }),
    fontWeight: '700',
    color: '#1A1A14',
    letterSpacing: -0.5,
  },
  wordItalic: { fontStyle: 'italic' },
});
