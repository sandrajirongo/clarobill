import { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import PdfThumbnail from 'react-native-pdf-thumbnail';

import { BrandLogo } from '@/components/brand-logo';
import { initBillUpload, putBillFile, triggerAnalysis } from '@/lib/api/bills';
import { ApiError } from '@/lib/api/client';

const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024; // 20MB — matches /api/bills/upload server-side limit
const ALLOWED_MIME_TYPES = ['application/pdf', 'image/jpeg', 'image/png'];

type PickedFile = {
  uri: string;
  name: string;
  size: number;
  mimeType: string;
  isImage: boolean;
  thumbnailUri?: string; // first-page thumbnail PNG, generated for PDFs
};

// iOS picker may return mimeType as null, "public.image" (UTI), or "image/heic".
// Derive a canonical mime type the engine can accept from whatever signal we have.
function resolveImageMime(
  mimeType: string | null | undefined,
  uri: string,
  fileName: string | null | undefined,
): string {
  const explicit = (mimeType ?? '').toLowerCase();
  if (explicit === 'image/jpeg' || explicit === 'image/png') return explicit;

  const ext = (fileName ?? uri).toLowerCase().split('?')[0].split('.').pop() ?? '';
  if (ext === 'jpg' || ext === 'jpeg' || ext === 'heic' || ext === 'heif') return 'image/jpeg';
  if (ext === 'png') return 'image/png';

  // Last resort: iOS picker assets without metadata are typically JPEG-compatible.
  return 'image/jpeg';
}

type UploadStep = 'uploading' | 'analyzing' | null;

type SubmissionResult = {
  billId: string;
  // null = analysis kicked off OK; string = upload OK but analysis failed (we keep the bill)
  analysisError: string | null;
};

export default function UploadScreen() {
  const [picked, setPicked] = useState<PickedFile | null>(null);
  const [isPicking, setIsPicking] = useState(false);
  const [step, setStep] = useState<UploadStep>(null);
  const [submission, setSubmission] = useState<SubmissionResult | null>(null);

  function validate(file: PickedFile): string | null {
    if (file.size > MAX_FILE_SIZE_BYTES) {
      return `File is too large. Max size is 20MB; this is ${(file.size / 1024 / 1024).toFixed(1)}MB.`;
    }
    if (!ALLOWED_MIME_TYPES.includes(file.mimeType)) {
      return `Unsupported file type. Use PDF, JPEG, or PNG.`;
    }
    return null;
  }

  async function handleTakePhoto() {
    setIsPicking(true);
    try {
      const perm = await ImagePicker.requestCameraPermissionsAsync();
      if (!perm.granted) {
        Alert.alert(
          'Camera permission needed',
          'Enable camera access in Settings to photograph your bill.'
        );
        return;
      }
      let result;
      try {
        result = await ImagePicker.launchCameraAsync({
          mediaTypes: ['images'],
          quality: 0.85,
        });
      } catch (e) {
        // iOS Simulator has no camera hardware. Real devices do.
        const msg = e instanceof Error ? e.message : String(e);
        Alert.alert(
          'Camera unavailable',
          msg.toLowerCase().includes('simulator') || msg.toLowerCase().includes('no available')
            ? 'The iOS Simulator does not have a camera. Try Choose from library, or test on a real device.'
            : msg
        );
        return;
      }
      if (result.canceled) return;
      const asset = result.assets[0];
      const file: PickedFile = {
        uri: asset.uri,
        name: asset.fileName ?? `bill-${Date.now()}.jpg`,
        size: asset.fileSize ?? 0,
        mimeType: resolveImageMime(asset.mimeType, asset.uri, asset.fileName),
        isImage: true,
      };
      const err = validate(file);
      if (err) {
        Alert.alert('Cannot use this photo', err);
        return;
      }
      setPicked(file);
    } finally {
      setIsPicking(false);
    }
  }

  async function handlePickFromLibrary() {
    setIsPicking(true);
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert(
          'Photo library permission needed',
          'Enable photo access in Settings to choose a bill image.'
        );
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.85,
      });
      if (result.canceled) return;
      const asset = result.assets[0];
      const file: PickedFile = {
        uri: asset.uri,
        name: asset.fileName ?? `bill-${Date.now()}.jpg`,
        size: asset.fileSize ?? 0,
        mimeType: resolveImageMime(asset.mimeType, asset.uri, asset.fileName),
        isImage: true,
      };
      const err = validate(file);
      if (err) {
        Alert.alert('Cannot use this image', err);
        return;
      }
      setPicked(file);
    } finally {
      setIsPicking(false);
    }
  }

  async function handlePickPdf() {
    setIsPicking(true);
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: 'application/pdf',
        copyToCacheDirectory: true,
      });
      if (result.canceled) return;
      const asset = result.assets[0];
      const file: PickedFile = {
        uri: asset.uri,
        name: asset.name,
        size: asset.size ?? 0,
        mimeType: asset.mimeType ?? 'application/pdf',
        isImage: false,
      };
      const err = validate(file);
      if (err) {
        Alert.alert('Cannot use this PDF', err);
        return;
      }

      // Render first page to a PNG thumbnail via iOS PDFKit. Best-effort —
      // if it fails (corrupt PDF, password-protected, etc.) we fall back to
      // the sage PDF badge in the preview component.
      try {
        const thumb = await PdfThumbnail.generate(asset.uri, 0);
        file.thumbnailUri = thumb.uri;
      } catch (e) {
        console.warn('PDF thumbnail generation failed:', e);
      }

      setPicked(file);
    } finally {
      setIsPicking(false);
    }
  }

  function handleClear() {
    setPicked(null);
    setSubmission(null);
    setStep(null);
  }

  async function handleUpload() {
    if (!picked) return;
    setStep('uploading');

    // Phase 1: upload. A failure here is fatal — nothing to fall back to.
    let billId: string;
    try {
      const init = await initBillUpload({
        fileName: picked.name,
        fileSize: picked.size,
        mimeType: picked.mimeType as 'application/pdf' | 'image/jpeg' | 'image/png',
      });
      billId = init.billId;
      await putBillFile({
        uploadUrl: init.uploadUrl,
        fileUri: picked.uri,
        mimeType: picked.mimeType,
      });
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.code}: ${e.detail}` : e instanceof Error ? e.message : String(e);
      Alert.alert('Upload failed', msg);
      setStep(null);
      return;
    }

    // Phase 2: kick off analysis. Failure here is NON-fatal — the file is
    // already safe in Storage and the bill row exists. We surface a warning
    // but treat the overall flow as a success so the user doesn't have to
    // re-upload. The engine can be retried later when the service is back.
    setStep('analyzing');
    let analysisError: string | null = null;
    try {
      await triggerAnalysis(billId);
    } catch (e) {
      analysisError =
        e instanceof ApiError ? `${e.code}: ${e.detail}` :
        e instanceof Error ? e.message : String(e);
    }

    setSubmission({ billId, analysisError });
    setStep(null);
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.brandRow}>
          <BrandLogo size="md" />
        </View>

        <View style={styles.body}>
          <Text style={styles.heading} accessibilityRole="header">
            Upload a bill
          </Text>
          <Text style={styles.bodyText}>
            Take a photo, choose an image from your library, or pick a PDF. We
            recommend uploading the itemized version of your bill so we can
            check every line.
          </Text>

          {picked ? (
            <PickedFilePreview
              file={picked}
              onClear={handleClear}
              onUpload={handleUpload}
              step={step}
              submission={submission}
            />
          ) : (
            <View style={styles.actions}>
              <ActionButton
                label="Take a photo"
                hint="Opens the camera"
                onPress={handleTakePhoto}
                disabled={isPicking}
              />
              <ActionButton
                label="Choose from library"
                hint="Opens your photo library"
                onPress={handlePickFromLibrary}
                disabled={isPicking}
              />
              <ActionButton
                label="Pick a PDF"
                hint="Opens the file picker"
                onPress={handlePickPdf}
                disabled={isPicking}
              />
            </View>
          )}

          <Text style={styles.note}>
            Selected files upload to Supabase Storage via a signed URL. Analysis
            kick-off + progress polling land in checkpoint 4d.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function ActionButton({
  label,
  hint,
  onPress,
  disabled,
}: {
  label: string;
  hint: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      accessibilityState={{ disabled }}
      style={({ pressed }) => [
        styles.actionBtn,
        pressed && styles.actionBtnPressed,
        disabled && styles.actionBtnDisabled,
      ]}
    >
      <Text style={styles.actionBtnText}>{label}</Text>
    </Pressable>
  );
}

function PickedFilePreview({
  file,
  onClear,
  onUpload,
  step,
  submission,
}: {
  file: PickedFile;
  onClear: () => void;
  onUpload: () => void;
  step: UploadStep;
  submission: SubmissionResult | null;
}) {
  const sizeKb = file.size / 1024;
  const sizeStr =
    sizeKb >= 1024 ? `${(sizeKb / 1024).toFixed(1)} MB` : `${sizeKb.toFixed(0)} KB`;
  const isSubmitted = Boolean(submission);
  const analysisDeferred = submission?.analysisError != null;
  const busy = step !== null;

  const eyebrow =
    step === 'uploading' ? 'UPLOADING…' :
    step === 'analyzing' ? 'ANALYZING…' :
    submission && !analysisDeferred ? 'SUBMITTED FOR ANALYSIS' :
    submission && analysisDeferred ? 'SAVED — ANALYSIS PENDING' :
    'READY TO UPLOAD';

  return (
    <View style={styles.preview}>
      <Text style={styles.previewEyebrow}>{eyebrow}</Text>

      {file.isImage ? (
        <Image
          source={{ uri: file.uri }}
          style={styles.previewImage}
          resizeMode="cover"
          accessibilityLabel="Preview of the selected bill image"
        />
      ) : file.thumbnailUri ? (
        <Image
          source={{ uri: file.thumbnailUri }}
          style={styles.previewImage}
          resizeMode="contain"
          accessibilityLabel="First-page preview of the selected PDF"
        />
      ) : (
        <View style={styles.pdfBadge}>
          <Text style={styles.pdfBadgeText}>PDF</Text>
        </View>
      )}

      <Text style={styles.previewName} numberOfLines={2}>
        {file.name}
      </Text>
      <Text style={styles.previewMeta}>
        {file.mimeType} · {sizeStr}
      </Text>

      {submission ? (
        <>
          <Text style={styles.billIdMeta} selectable>
            Bill ID: {submission.billId}
          </Text>
          {analysisDeferred ? (
            <Text style={styles.statusHintWarn}>
              Your bill is saved. We couldn&rsquo;t start the analysis right
              now (the service is temporarily unavailable). It will retry
              automatically — no need to upload again.
            </Text>
          ) : (
            <Text style={styles.statusHint}>
              Analysis is running in the background. The bill will appear on
              the Home tab when it&rsquo;s ready (status polling lands in 4e).
            </Text>
          )}
        </>
      ) : null}

      <View style={styles.previewActions}>
        <Pressable
          onPress={onClear}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel={isSubmitted ? 'Upload another bill' : 'Choose a different file'}
          style={({ pressed }) => [
            styles.secondaryBtn,
            pressed && styles.actionBtnPressed,
            busy && styles.actionBtnDisabled,
          ]}
        >
          <Text style={styles.secondaryBtnText}>
            {isSubmitted ? 'Upload another bill' : 'Choose a different file'}
          </Text>
        </Pressable>

        {!isSubmitted ? (
          <Pressable
            onPress={onUpload}
            disabled={busy}
            accessibilityRole="button"
            accessibilityLabel="Upload bill"
            accessibilityState={{ disabled: busy, busy }}
            style={({ pressed }) => [
              styles.actionBtn,
              pressed && styles.actionBtnPressed,
              busy && styles.actionBtnDisabled,
            ]}
          >
            {busy ? (
              <ActivityIndicator color="#ffffff" />
            ) : (
              <Text style={styles.actionBtnText}>Upload bill</Text>
            )}
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F4F2EC' },
  scroll: { paddingHorizontal: 24, paddingBottom: 32 },
  brandRow: { alignItems: 'center', paddingVertical: 16, marginBottom: 24 },
  body: { width: '100%', maxWidth: 420, alignSelf: 'center' },
  heading: {
    fontFamily: Platform.select({ ios: 'Georgia', android: 'serif' }),
    fontSize: 32,
    fontWeight: '700',
    color: '#1A1A14',
    letterSpacing: -0.6,
    marginBottom: 12,
  },
  bodyText: { fontSize: 15, color: '#5A5A50', lineHeight: 22, marginBottom: 24 },
  actions: { gap: 12, marginBottom: 24 },
  actionBtn: {
    backgroundColor: '#2D4A2A',
    borderRadius: 999,
    paddingVertical: 16,
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionBtnPressed: { opacity: 0.85 },
  actionBtnDisabled: { opacity: 0.5 },
  actionBtnText: { color: '#ffffff', fontWeight: '700', fontSize: 16 },
  secondaryBtn: {
    backgroundColor: 'transparent',
    borderRadius: 999,
    paddingVertical: 14,
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: '#2D4A2A',
  },
  secondaryBtnText: { color: '#2D4A2A', fontWeight: '700', fontSize: 15 },
  note: { fontSize: 12, color: '#9A9A8E', lineHeight: 18, fontStyle: 'italic', marginTop: 8 },

  preview: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 20,
    marginBottom: 24,
    borderWidth: 1,
    borderColor: '#E2DDD4',
  },
  previewEyebrow: {
    fontSize: 12,
    fontWeight: '700',
    color: '#2D4A2A',
    letterSpacing: 1.2,
    marginBottom: 12,
  },
  previewImage: {
    width: '100%',
    height: 220,
    borderRadius: 12,
    marginBottom: 14,
    backgroundColor: '#F4F2EC',
  },
  pdfBadge: {
    width: '100%',
    height: 100,
    borderRadius: 12,
    marginBottom: 14,
    backgroundColor: '#2D4A2A',
    alignItems: 'center',
    justifyContent: 'center',
  },
  pdfBadgeText: {
    color: '#C8F060',
    fontFamily: Platform.select({ ios: 'Georgia', android: 'serif' }),
    fontWeight: '700',
    fontSize: 32,
    letterSpacing: 4,
  },
  previewName: {
    fontSize: 15,
    fontWeight: '700',
    color: '#1A1A14',
    marginBottom: 4,
  },
  previewMeta: {
    fontSize: 13,
    color: '#9A9A8E',
    marginBottom: 8,
  },
  billIdMeta: {
    fontSize: 12,
    color: '#2D4A2A',
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    marginBottom: 10,
  },
  statusHint: {
    fontSize: 13,
    color: '#5A5A50',
    lineHeight: 19,
    marginBottom: 16,
  },
  statusHintWarn: {
    fontSize: 13,
    color: '#7A5A1A',
    backgroundColor: '#F4EEDC',
    lineHeight: 19,
    padding: 12,
    borderRadius: 8,
    marginBottom: 16,
  },
  previewActions: { gap: 10 },
});
